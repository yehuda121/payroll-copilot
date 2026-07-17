/**
 * UI end-to-end audit with Playwright. Reports only failures.
 * Run: node _audit/ui_audit.mjs
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const FRONT = process.env.AUDIT_FRONT || 'http://localhost:3000';
const API = process.env.AUDIT_API || 'http://localhost:8000/api/v1';
const findings = [];

function add(severity, area, summary, detail = '', evidence = {}) {
  findings.push({ severity, area, summary, detail, evidence });
  console.log(`[${severity}] ${area}: ${summary}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ locale: 'he-IL' });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  page.on('response', (resp) => {
    const url = resp.url();
    if (!url.includes('localhost:8000') && !url.includes('localhost:3000')) return;
    if (resp.status() >= 500) {
      failedRequests.push({ url, status: resp.status() });
    }
  });

  // Landing
  try {
    await page.goto(FRONT + '/', { waitUntil: 'networkidle', timeout: 60000 });
    const chat = page.locator('textarea, input[type="text"], [contenteditable="true"]').first();
    const hasChat = await chat.count().then((c) => c > 0).catch(() => false);
    // GuestLandingChat may use a specific class
    const bodyText = await page.locator('body').innerText();
    if (!bodyText || bodyText.trim().length < 10) {
      add('broken_flow', 'ui_landing', 'Landing page rendered empty body');
    }
    // Try send a short message if composer exists
    const composer = page.locator('textarea').first();
    if (await composer.count()) {
      await composer.fill('שלום');
      const send = page.getByRole('button').filter({ hasText: /send|שלח|Send/i }).first();
      if (await send.count()) {
        await send.click();
        await page.waitForTimeout(8000);
      } else {
        // try Enter
        await composer.press('Enter');
        await page.waitForTimeout(8000);
      }
    } else {
      add('broken_flow', 'ui_landing', 'Landing chat composer (textarea) not found');
    }
  } catch (e) {
    add('exception', 'ui_landing', 'Landing flow exception', String(e));
  }

  // Login / role picker
  try {
    await page.goto(FRONT + '/login', { waitUntil: 'networkidle', timeout: 60000 });
    const roles = page.locator('.dev-role-card, button');
    const roleButtons = page.getByRole('button');
    const count = await roleButtons.count();
    if (count < 1) {
      add('broken_flow', 'ui_login', 'Login page has no role/login buttons');
    } else {
      // Click employee-ish button
      const employeeBtn = page.locator('.dev-role-card').filter({ hasText: /Employee|עובד|employee/i }).first();
      if (await employeeBtn.count()) {
        await employeeBtn.click();
        await page.waitForTimeout(3000);
        const url = page.url();
        if (!url.includes('/employee')) {
          add('broken_flow', 'ui_employee_login', `Employee role login did not navigate to /employee (url=${url})`);
        }
        // Check for error dialogs
        const dialog = page.locator('[role="dialog"], .dialog');
        if (await dialog.count()) {
          const text = await dialog.innerText().catch(() => '');
          if (/token|failed|error|could not|חסר/i.test(text)) {
            add('broken_flow', 'ui_employee_login', 'Employee login showed error dialog', text.slice(0, 500));
          }
        }
        // Employee dashboard content
        const body = await page.locator('body').innerText();
        if (/employee_not_found|not found|404/i.test(body)) {
          add('broken_flow', 'ui_employee_portal', 'Employee portal shows not-found error', body.slice(0, 400));
        }
        // Navigate documents
        await page.goto(FRONT + '/employee/documents', { waitUntil: 'networkidle', timeout: 30000 }).catch((e) => {
          add('exception', 'ui_employee_documents', String(e));
        });
        await page.waitForTimeout(1500);
        const docsBody = await page.locator('body').innerText();
        if (/employee_not_found|Bound employee record was not found/i.test(docsBody)) {
          add(
            'broken_flow',
            'ui_employee_documents',
            'Employee documents page reflects missing bound employee',
            docsBody.slice(0, 400),
          );
        }
        await page.goto(FRONT + '/employee/upload', { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
        await page.waitForTimeout(1000);
      } else {
        // Cognito form mode
        const email = page.locator('input[type="email"], input[name="email"]');
        if (await email.count()) {
          add(
            'missing_config',
            'ui_login',
            'Login shows Cognito form (dev role picker disabled) — Cognito not usable without pool config',
          );
        } else {
          add('broken_flow', 'ui_login', 'Neither dev role cards nor Cognito email field found');
        }
      }
    }
  } catch (e) {
    add('exception', 'ui_login', 'Login UI exception', String(e));
  }

  // Accountant via role picker
  try {
    await page.goto(FRONT + '/login', { waitUntil: 'networkidle', timeout: 60000 });
    const accBtn = page.locator('.dev-role-card').filter({ hasText: /Accountant|חשב|payroll/i }).first();
    if (await accBtn.count()) {
      await accBtn.click();
      await page.waitForTimeout(2500);
      if (!page.url().includes('/accountant')) {
        add('broken_flow', 'ui_accountant_login', `Accountant login did not reach /accountant (url=${page.url()})`);
      }
      await page.goto(FRONT + '/accountant/employees', { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(2000);
      const body = await page.locator('body').innerText();
      // Empty list is ok; hard errors are not
      if (/TypeError|Unhandled|500|Internal Server/i.test(body)) {
        add('broken_flow', 'ui_accountant_employees', 'Accountant employees page shows hard error', body.slice(0, 400));
      }
      // Check API call result via page responses already collected
      await page.goto(FRONT + '/accountant/bulk-upload', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.goto(FRONT + '/accountant/rules', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.goto(FRONT + '/accountant/findings', { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.goto(FRONT + '/accountant/approvals', { waitUntil: 'domcontentloaded', timeout: 30000 });
    }
  } catch (e) {
    add('exception', 'ui_accountant', 'Accountant UI exception', String(e));
  }

  // Admin
  try {
    await page.goto(FRONT + '/login', { waitUntil: 'networkidle', timeout: 60000 });
    const adminBtn = page.locator('.dev-role-card').filter({ hasText: /Admin|מנהל|developer/i }).first();
    if (await adminBtn.count()) {
      await adminBtn.click();
      await page.waitForTimeout(2500);
      if (!page.url().includes('/admin')) {
        add('broken_flow', 'ui_admin_login', `Admin login did not reach /admin (url=${page.url()})`);
      }
      await page.goto(FRONT + '/admin/document-lab', { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(2000);
      const body = await page.locator('body').innerText();
      if (/404|not available|Not Found/i.test(body) && body.length < 800) {
        add('broken_flow', 'ui_document_lab', 'Document Lab page appears unavailable', body.slice(0, 400));
      }
    }
  } catch (e) {
    add('exception', 'ui_admin', 'Admin UI exception', String(e));
  }

  // Signup
  try {
    await page.goto(FRONT + '/signup', { waitUntil: 'networkidle', timeout: 30000 });
    const body = await page.locator('body').innerText();
    if (!body.trim()) add('broken_flow', 'ui_signup', 'Signup page empty');
  } catch (e) {
    add('exception', 'ui_signup', 'Signup page exception', String(e));
  }

  // Aggregate console / page errors (filter noise)
  const seriousConsole = consoleErrors.filter(
    (t) => !/favicon|Download the React DevTools|React Router Future Flag/i.test(t),
  );
  for (const t of seriousConsole.slice(0, 20)) {
    add('exception', 'ui_console', 'Browser console error', t.slice(0, 800));
  }
  for (const t of pageErrors.slice(0, 10)) {
    add('exception', 'ui_pageerror', 'Unhandled page exception', t.slice(0, 800));
  }
  for (const fr of failedRequests.slice(0, 20)) {
    add('error', 'ui_api', `UI triggered HTTP ${fr.status}`, fr.url);
  }

  await browser.close();

  const out = path.join('_audit', 'ui_findings.json');
  fs.mkdirSync('_audit', { recursive: true });
  fs.writeFileSync(
    out,
    JSON.stringify({ generated_at: new Date().toISOString(), finding_count: findings.length, findings }, null, 2),
    'utf8',
  );
  console.log(JSON.stringify({ finding_count: findings.length, out }));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
