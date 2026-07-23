import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useEmployeeSession } from '../auth/EmployeeSessionContext';
import {
  emptyAppendixChildren,
  emptyFixedFieldValues,
  fixedFieldKeysFor,
  ID_APPENDIX_CHILDREN_KEY,
  isAppendixDocumentType,
  parseAppendixChildren,
  type AppendixChild,
} from '../lib/employee/document-fixed-forms';
import { validateUploadFile } from '../lib/guest/upload-guardrails';
import { ApiClientError } from '../services/api';
import { useEmployeeWorkspace } from '../features/employee/EmployeeWorkspaceContext';
import {
  type EmployeeDocumentCenterItem,
  type EmployeeDocumentForm,
} from '../services/employeePortal';
import type { DocumentLanguage, ExtractedPayslipField } from '../types/api';
import type { FieldDraft } from './useEmployeePayslipFlow';

export type PersistentDocumentType = 'national_id' | 'id_appendix' | 'contract';
export type DocumentWorkspaceTab = 'upload' | 'digital' | 'original';
export type DocumentBusyPhase = 'extracting' | 'saving' | 'deleting' | null;

function serializeFieldValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '';
    }
  }
  return String(value);
}

function fieldsFromFixedValues(values: Record<string, string>): ExtractedPayslipField[] {
  return Object.entries(values).map(([key, value]) => ({
    key,
    value,
    confidence: null,
    source_text: null,
    status: value.trim() ? 'FOUND' : 'MISSING',
    edited_by_user: true,
  }));
}

function fieldsFromAppendixChildren(children: AppendixChild[]): ExtractedPayslipField[] {
  return [
    {
      key: ID_APPENDIX_CHILDREN_KEY,
      value: children,
      confidence: null,
      source_text: null,
      status: children.length > 0 ? 'FOUND' : 'MISSING',
      edited_by_user: true,
    },
  ];
}

/**
 * Employee My Documents workspace for a single persistent document type.
 */
export function useEmployeeDocumentWorkspace(documentType: PersistentDocumentType) {
  const { api: workspaceApi } = useEmployeeWorkspace();
  const session = useEmployeeSession();
  const { t } = useTranslation();
  const fixedKeys = fixedFieldKeysFor(documentType);
  const usesFixedForm = fixedKeys !== null;
  const usesAppendixForm = isAppendixDocumentType(documentType);

  const [item, setItem] = useState<EmployeeDocumentCenterItem | null>(() => {
    const center = session.getDocumentCenter();
    return center?.persistent_documents.find((row) => row.document_type === documentType) ?? null;
  });
  /** True only when there is nothing yet to paint for this document type. */
  const [loading, setLoading] = useState(() => session.getDocumentCenter() == null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [tab, setTab] = useState<DocumentWorkspaceTab>('digital');
  const [busyPhase, setBusyPhase] = useState<DocumentBusyPhase>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('he');
  const [fields, setFields] = useState<ExtractedPayslipField[]>([]);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [fixedValues, setFixedValues] = useState<Record<string, string>>(() =>
    emptyFixedFieldValues(documentType),
  );
  const [appendixChildren, setAppendixChildren] = useState<AppendixChild[]>(() =>
    emptyAppendixChildren(),
  );
  const [formDirty, setFormDirty] = useState(false);
  /** Apply default inner-tab once per document-type selection after load settles. */
  const pendingDefaultTabRef = useRef(true);
  const documentTypeRef = useRef(documentType);
  documentTypeRef.current = documentType;

  const applyForm = useCallback(
    (form: EmployeeDocumentForm) => {
      if (usesAppendixForm) {
        const childField = form.fields.find((field) => field.key === ID_APPENDIX_CHILDREN_KEY);
        const children = parseAppendixChildren(childField?.value);
        setAppendixChildren(children);
        setFields(fieldsFromAppendixChildren(children));
        setFixedValues({});
        setFieldDrafts({});
      } else if (usesFixedForm && fixedKeys) {
        const next = emptyFixedFieldValues(documentType);
        for (const field of form.fields) {
          if (fixedKeys.includes(field.key as (typeof fixedKeys)[number])) {
            next[field.key] = serializeFieldValue(field.value);
          }
        }
        setFixedValues(next);
        setFields(fieldsFromFixedValues(next));
        setAppendixChildren(emptyAppendixChildren());
        setFieldDrafts({});
      } else {
        setFields(form.fields);
        setFixedValues({});
        setAppendixChildren(emptyAppendixChildren());
        setFieldDrafts(
          Object.fromEntries(
            form.fields.map((field) => [
              field.key,
              {
                value: serializeFieldValue(field.value),
                dirty: false,
                clear: false,
              },
            ]),
          ),
        );
      }
      setFormDirty(false);
    },
    [documentType, fixedKeys, usesAppendixForm, usesFixedForm],
  );

  const resetFormState = useCallback(() => {
    if (usesAppendixForm) {
      const empty = emptyAppendixChildren();
      setAppendixChildren(empty);
      setFields(fieldsFromAppendixChildren(empty));
      setFixedValues({});
    } else if (usesFixedForm) {
      const empty = emptyFixedFieldValues(documentType);
      setFixedValues(empty);
      setFields(fieldsFromFixedValues(empty));
      setAppendixChildren(emptyAppendixChildren());
    } else {
      setFields([]);
      setFixedValues({});
      setAppendixChildren(emptyAppendixChildren());
    }
    setFieldDrafts({});
    setFormDirty(false);
  }, [documentType, usesAppendixForm, usesFixedForm]);

  const refresh = useCallback(async () => {
    setError(null);

    const paintFromCenter = (center: Awaited<ReturnType<typeof workspaceApi.listDocuments>>) => {
      session.setDocumentCenter(center);
      const next =
        center.persistent_documents.find((row) => row.document_type === documentType) ?? null;
      setItem(next);
      return next;
    };

    const applyCachedOrEmptyForm = async (next: EmployeeDocumentCenterItem | null) => {
      if (next?.document_id) {
        const cachedForm = session.getDocumentForm(next.document_id);
        if (cachedForm) {
          applyForm(cachedForm);
          return;
        }
      } else {
        const byType = session.getDocumentFormByType(documentType);
        if (byType) {
          applyForm(byType);
          return;
        }
      }
    };

    const cachedCenter = session.getDocumentCenter();
    if (cachedCenter) {
      const next = paintFromCenter(cachedCenter);
      await applyCachedOrEmptyForm(next);
      setLoading(false);
    } else {
      setLoading(true);
    }

    setRefreshing(true);
    try {
      const center = await workspaceApi.listDocuments();
      const next = paintFromCenter(center);

      if (next?.document_id) {
        try {
          const form = await workspaceApi.getEmployeeDocumentForm(next.document_id);
          session.setDocumentForm(form);
          applyForm(form);
        } catch (formError) {
          if (!(formError instanceof ApiClientError && formError.status === 404)) {
            throw formError;
          }
          session.invalidateDocumentForm(next.document_id);
          if (usesFixedForm || usesAppendixForm) {
            resetFormState();
          } else {
            setFields([]);
            setFieldDrafts({});
            setFormDirty(false);
          }
        }
      } else {
        const byType = session.getDocumentFormByType(documentType);
        if (byType) {
          applyForm(byType);
        } else if (usesFixedForm || usesAppendixForm) {
          resetFormState();
        } else {
          setFields([]);
          setFieldDrafts({});
          setFormDirty(false);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
      if (!cachedCenter) setItem(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
      // Only the in-flight refresh for the current document type may settle the default tab.
      if (pendingDefaultTabRef.current && documentTypeRef.current === documentType) {
        pendingDefaultTabRef.current = false;
        const center = session.getDocumentCenter();
        const resolved =
          center?.persistent_documents.find((row) => row.document_type === documentType) ?? null;
        const hasExistingDocument = Boolean(resolved?.exists && resolved.document_id);
        if (!hasExistingDocument) {
          setTab('upload');
        }
      }
    }
  }, [
    applyForm,
    documentType,
    resetFormState,
    session,
    t,
    usesAppendixForm,
    usesFixedForm,
    workspaceApi,
  ]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setTab('digital');
    pendingDefaultTabRef.current = true;
    setPendingFile(null);
    setFileError(null);
    setStatusMessage(null);
    setError(null);
    setDocumentLanguage('he');
  }, [documentType]);

  const selectFile = useCallback(
    async (file: File | null) => {
      setFileError(null);
      setError(null);
      if (!file) {
        setPendingFile(null);
        return;
      }
      const result = await validateUploadFile(
        documentType === 'id_appendix' ? 'national_id' : documentType,
        file,
        [],
        t,
      );
      if (!result.ok) {
        setPendingFile(null);
        setFileError(result.message);
        return;
      }
      setPendingFile(file);
      setTab('upload');
    },
    [documentType, t],
  );

  const deleteSelectedFile = useCallback(() => {
    setPendingFile(null);
    setFileError(null);
  }, []);

  const extractDocument = useCallback(
    async (fileOverride?: File) => {
      const file = fileOverride ?? pendingFile;
      if (!file) {
        setError(t('employee.documents.uploadRequired'));
        return;
      }
      setBusyPhase('extracting');
      setStatusMessage(t('employee.documents.extracting'));
      setError(null);
      try {
        const form = await workspaceApi.extractEmployeeDocument(file, {
          documentType,
          language: documentLanguage,
        });
        session.setDocumentForm(form);
        session.setDocumentFormByType(documentType, form);
        session.invalidateDocumentCenter();
        applyForm(form);
        setPendingFile(null);
        await refresh();
        setTab('digital');
      } catch (err) {
        setError(
          err instanceof ApiClientError || err instanceof Error ? err.message : t('common.error'),
        );
      } finally {
        setBusyPhase(null);
        setStatusMessage(null);
      }
    },
    [applyForm, pendingFile, documentType, documentLanguage, refresh, session, t, workspaceApi],
  );

  const deleteOwnedDocument = useCallback(
    async (scope: 'original' | 'digital' | 'both' = 'both') => {
      if (!item?.document_id) return;
      setBusyPhase('deleting');
      setError(null);
      try {
        await workspaceApi.deleteOwnedDocument(item.document_id, scope);
        session.invalidateDocumentForm(item.document_id);
        session.invalidateDocumentFormByType(documentType);
        session.invalidateDocumentCenter();
        setPendingFile(null);
        resetFormState();
        await refresh();
        setTab('upload');
      } catch (err) {
        setError(
          err instanceof ApiClientError || err instanceof Error ? err.message : t('common.error'),
        );
      } finally {
        setBusyPhase(null);
      }
    },
    [documentType, item?.document_id, refresh, resetFormState, session, t, workspaceApi],
  );

  const updateFieldDraft = useCallback(
    (key: string, value: string) => {
      setFormDirty(true);
      if (usesFixedForm) {
        setFixedValues((prev) => ({ ...prev, [key]: value }));
        setFields((prev) => {
          const exists = prev.some((field) => field.key === key);
          if (exists) {
            return prev.map((field) =>
              field.key === key
                ? {
                    ...field,
                    value,
                    status: value.trim() ? 'FOUND' : 'MISSING',
                    edited_by_user: true,
                  }
                : field,
            );
          }
          return [
            ...prev,
            {
              key,
              value,
              confidence: null,
              source_text: null,
              status: value.trim() ? 'FOUND' : 'MISSING',
              edited_by_user: true,
            },
          ];
        });
        return;
      }
      setFieldDrafts((prev) => ({
        ...prev,
        [key]: { value, dirty: true, clear: false },
      }));
      setFields((prev) => {
        const exists = prev.some((field) => field.key === key);
        if (exists) {
          return prev.map((field) => (field.key === key ? { ...field, value } : field));
        }
        return [
          ...prev,
          {
            key,
            value,
            confidence: null,
            source_text: null,
            status: 'FOUND',
            edited_by_user: true,
          },
        ];
      });
    },
    [usesFixedForm],
  );

  const clearFieldDraft = useCallback((key: string) => {
    setFormDirty(true);
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value: '', dirty: true, clear: true },
    }));
  }, []);

  const removeField = useCallback((key: string) => {
    setFormDirty(true);
    setFields((prev) => prev.filter((field) => field.key !== key));
    setFieldDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const addField = useCallback(() => {
    setFormDirty(true);
    const key = `custom_field_${Date.now()}`;
    setFields((prev) => [
      ...prev,
      {
        key,
        value: '',
        confidence: null,
        source_text: null,
        status: 'FOUND',
        edited_by_user: true,
      },
    ]);
    setFieldDrafts((prev) => ({
      ...prev,
      [key]: { value: '', dirty: true, clear: false },
    }));
  }, []);

  const addChild = useCallback(() => {
    setFormDirty(true);
    setAppendixChildren((prev) => {
      const next = [...prev, { name: '', birth_date: '' }];
      setFields(fieldsFromAppendixChildren(next));
      return next;
    });
  }, []);

  const removeChild = useCallback((index: number) => {
    setFormDirty(true);
    setAppendixChildren((prev) => {
      const next = prev.filter((_, i) => i !== index);
      setFields(fieldsFromAppendixChildren(next));
      return next;
    });
  }, []);

  const updateChild = useCallback((index: number, patch: Partial<AppendixChild>) => {
    setFormDirty(true);
    setAppendixChildren((prev) => {
      const next = prev.map((child, i) => (i === index ? { ...child, ...patch } : child));
      setFields(fieldsFromAppendixChildren(next));
      return next;
    });
  }, []);

  const saveDigitalForm = useCallback(
    async (options?: { appendixChildrenOverride?: AppendixChild[] }) => {
      setBusyPhase('saving');
      setStatusMessage(t('employee.documents.savingDigitalForm'));
      setError(null);
      try {
        const childrenForSave = options?.appendixChildrenOverride ?? appendixChildren;
        if (options?.appendixChildrenOverride) {
          setAppendixChildren(options.appendixChildrenOverride);
          setFields(fieldsFromAppendixChildren(options.appendixChildrenOverride));
        }
        const payload = usesAppendixForm
          ? [
              {
                key: ID_APPENDIX_CHILDREN_KEY,
                value: childrenForSave,
                original_value: childrenForSave,
              },
            ]
          : usesFixedForm
            ? Object.entries(fixedValues).map(([key, value]) => ({
                key,
                value,
                original_value: value,
              }))
            : fields.map((field) => ({
                key: field.key,
                value: fieldDrafts[field.key]?.value ?? serializeFieldValue(field.value),
                source_text: field.source_text,
                original_value: field.value,
              }));

        const form = item?.document_id
          ? await workspaceApi.saveEmployeeDocumentForm(item.document_id, payload)
          : await workspaceApi.saveEmployeeDocumentFormByType(documentType, payload);

        session.setDocumentForm(form);
        session.setDocumentFormByType(documentType, form);
        session.invalidateDocumentCenter();
        applyForm(form);
        await refresh();
        setStatusMessage(t('employee.documents.digitalFormSaved'));
        return true;
      } catch (err) {
        setError(
          err instanceof ApiClientError || err instanceof Error ? err.message : t('common.error'),
        );
        return false;
      } finally {
        setBusyPhase(null);
      }
    },
    [
      applyForm,
      appendixChildren,
      documentType,
      fieldDrafts,
      fields,
      fixedValues,
      item?.document_id,
      refresh,
      session,
      t,
      usesAppendixForm,
      usesFixedForm,
      workspaceApi,
    ],
  );

  const draftsForForm = useMemo(() => {
    const next: Record<string, FieldDraft> = { ...fieldDrafts };
    for (const field of fields) {
      if (!next[field.key]) {
        next[field.key] = {
          value: serializeFieldValue(field.value),
          dirty: Boolean(field.edited_by_user),
          clear: false,
        };
      }
    }
    return next;
  }, [fieldDrafts, fields]);

  const isBusy = busyPhase !== null;
  const hasDocument = Boolean(
    (item?.has_original_file ?? item?.exists) && item.document_id,
  );
  const hasDigitalForm = Boolean(
    item?.document_id &&
      item.extraction_status !== 'missing' &&
      item.extraction_status !== 'extraction_not_connected',
  );
  const hasDirtyFields =
    formDirty || Object.values(fieldDrafts).some((draft) => draft.dirty);

  return {
    item,
    loading,
    refreshing,
    error,
    statusMessage,
    tab,
    setTab,
    busyPhase,
    isBusy,
    pendingFile,
    fileError,
    documentLanguage,
    setDocumentLanguage,
    selectFile,
    deleteSelectedFile,
    extractDocument,
    deleteOwnedDocument,
    saveDigitalForm,
    fields,
    fieldDrafts: draftsForForm,
    fixedValues,
    appendixChildren,
    usesFixedForm,
    usesAppendixForm,
    updateFieldDraft,
    clearFieldDraft,
    removeField,
    addField,
    addChild,
    removeChild,
    updateChild,
    hasDocument,
    hasDigitalForm,
    hasDirtyFields,
    refresh,
  };
}
