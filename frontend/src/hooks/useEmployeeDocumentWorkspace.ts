import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  emptyFixedFieldValues,
  fixedFieldKeysFor,
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

/**
 * Employee My Documents workspace for a single persistent document type.
 */
export function useEmployeeDocumentWorkspace(documentType: PersistentDocumentType) {
  const { api: workspaceApi } = useEmployeeWorkspace();
  const { t } = useTranslation();
  const fixedKeys = fixedFieldKeysFor(documentType);
  const usesFixedForm = fixedKeys !== null;

  const [item, setItem] = useState<EmployeeDocumentCenterItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [tab, setTab] = useState<DocumentWorkspaceTab>('upload');
  const [busyPhase, setBusyPhase] = useState<DocumentBusyPhase>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [documentLanguage, setDocumentLanguage] = useState<DocumentLanguage>('he');
  const [fields, setFields] = useState<ExtractedPayslipField[]>([]);
  const [fieldDrafts, setFieldDrafts] = useState<Record<string, FieldDraft>>({});
  const [fixedValues, setFixedValues] = useState<Record<string, string>>(() =>
    emptyFixedFieldValues(documentType),
  );
  const [formDirty, setFormDirty] = useState(false);

  const applyForm = useCallback(
    (form: EmployeeDocumentForm) => {
      if (usesFixedForm && fixedKeys) {
        const next = emptyFixedFieldValues(documentType);
        for (const field of form.fields) {
          if (fixedKeys.includes(field.key as (typeof fixedKeys)[number])) {
            next[field.key] = serializeFieldValue(field.value);
          }
        }
        setFixedValues(next);
        setFields(fieldsFromFixedValues(next));
        setFieldDrafts({});
      } else {
        setFields(form.fields);
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
    [documentType, fixedKeys, usesFixedForm],
  );

  const resetFormState = useCallback(() => {
    if (usesFixedForm) {
      const empty = emptyFixedFieldValues(documentType);
      setFixedValues(empty);
      setFields(fieldsFromFixedValues(empty));
    } else {
      setFields([]);
      setFixedValues({});
    }
    setFieldDrafts({});
    setFormDirty(false);
  }, [documentType, usesFixedForm]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const center = await workspaceApi.listDocuments();
      const next =
        center.persistent_documents.find((row) => row.document_type === documentType) ?? null;
      setItem(next);
      if (next?.document_id) {
        try {
          applyForm(await workspaceApi.getEmployeeDocumentForm(next.document_id));
        } catch (formError) {
          if (!(formError instanceof ApiClientError && formError.status === 404)) {
            throw formError;
          }
          if (usesFixedForm) {
            resetFormState();
          } else {
            setFields([]);
            setFieldDrafts({});
            setFormDirty(false);
          }
        }
      } else if (usesFixedForm) {
        resetFormState();
      } else {
        setFields([]);
        setFieldDrafts({});
        setFormDirty(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.error'));
      setItem(null);
    } finally {
      setLoading(false);
    }
  }, [applyForm, documentType, resetFormState, t, usesFixedForm, workspaceApi]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setTab('upload');
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

  const extractDocument = useCallback(async () => {
    if (!pendingFile) {
      setError(t('employee.documents.uploadRequired'));
      return;
    }
    setBusyPhase('extracting');
    setStatusMessage(t('employee.documents.extracting'));
    setError(null);
    try {
      const form = await workspaceApi.extractEmployeeDocument(pendingFile, {
        documentType,
        language: documentLanguage,
      });
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
  }, [applyForm, pendingFile, documentType, documentLanguage, refresh, t, workspaceApi]);

  const deleteOwnedDocument = useCallback(async () => {
    if (!item?.document_id) return;
    setBusyPhase('deleting');
    setError(null);
    try {
      await workspaceApi.deleteOwnedDocument(item.document_id);
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
  }, [item?.document_id, refresh, resetFormState, t, workspaceApi]);

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

  const saveDigitalForm = useCallback(async () => {
    setBusyPhase('saving');
    setStatusMessage(t('employee.documents.savingDigitalForm'));
    setError(null);
    try {
      const payload = usesFixedForm
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

      applyForm(form);
      await refresh();
      setStatusMessage(t('employee.documents.digitalFormSaved'));
    } catch (err) {
      setError(
        err instanceof ApiClientError || err instanceof Error ? err.message : t('common.error'),
      );
    } finally {
      setBusyPhase(null);
    }
  }, [
    applyForm,
    documentType,
    fieldDrafts,
    fields,
    fixedValues,
    item?.document_id,
    refresh,
    t,
    usesFixedForm,
    workspaceApi,
  ]);

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
  const hasDocument = Boolean(item?.exists && item.document_id);
  const hasDigitalForm = usesFixedForm
    ? true
    : Boolean(
        item?.document_id &&
          item.extraction_status !== 'missing' &&
          item.extraction_status !== 'extraction_not_connected',
      );
  const hasDirtyFields =
    formDirty || Object.values(fieldDrafts).some((draft) => draft.dirty);

  return {
    item,
    loading,
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
    usesFixedForm,
    updateFieldDraft,
    clearFieldDraft,
    removeField,
    addField,
    hasDocument,
    hasDigitalForm,
    hasDirtyFields,
    refresh,
  };
}
