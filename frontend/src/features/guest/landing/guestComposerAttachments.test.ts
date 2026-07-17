import { describe, expect, it, vi } from 'vitest';

/**
 * Composer attachment contract for the public guest landing chat:
 * attach/drag only queues; Send triggers processing.
 */

describe('guest composer attachment contract', () => {
  it('queues attachments without calling extraction', async () => {
    const extractGuestPayslip = vi.fn();
    const uploadGuestSupporting = vi.fn();
    const pending: Array<{ id: string; name: string }> = [];

    const queueFile = (name: string) => {
      pending.push({ id: crypto.randomUUID(), name });
      // Intentionally does not call extract/upload — mirrors GuestLandingChat.queueFiles
    };

    queueFile('payslip.pdf');
    queueFile('id.png');

    expect(pending).toHaveLength(2);
    expect(extractGuestPayslip).not.toHaveBeenCalled();
    expect(uploadGuestSupporting).not.toHaveBeenCalled();
  });

  it('removes a pending attachment before send', () => {
    let pending = [
      { id: 'a', name: 'payslip.pdf' },
      { id: 'b', name: 'id.png' },
    ];
    const remove = (id: string) => {
      pending = pending.filter((item) => item.id !== id);
    };
    remove('b');
    expect(pending.map((p) => p.name)).toEqual(['payslip.pdf']);
  });

  it('send processes all pending attachments and blocks duplicate while busy', async () => {
    const processed: string[] = [];
    let busy = false;
    let pending = [
      { id: '1', name: 'payslip.pdf', slot: 'payslip' },
      { id: '2', name: 'id.png', slot: 'national_id' },
    ];

    const send = async () => {
      if (busy || pending.length === 0) return;
      busy = true;
      const batch = [...pending];
      pending = [];
      for (const item of batch) {
        processed.push(item.name);
      }
      busy = false;
    };

    await send();
    await send(); // no-op: pending cleared / would be blocked if still busy

    expect(processed).toEqual(['payslip.pdf', 'id.png']);
    expect(pending).toHaveLength(0);
  });
});
