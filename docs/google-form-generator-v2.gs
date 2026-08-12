function createUncleClarificationFormV2() {
  const form = FormApp.create('Office Ticket OCR - Clarification Questionnaire (Full)');
  form.setDescription(
    'Please answer these so we can finalize the office-side prototype.\n\n' +
    'Already Assumed:\n' +
    '- Current process is manual\n' +
    '- Tickets are handwritten\n' +
    '- Review happens on same screen as image preview\n' +
    '- Low-confidence fields highlighted\n' +
    '- Invoice work is in scope immediately\n' +
    '- On-prem export in Phase 1 preferred if feasible'
  );

  function addSection(title) {
    form.addPageBreakItem().setTitle(title);
  }

  function addParagraph(title, required) {
    form.addParagraphTextItem().setTitle(title).setRequired(Boolean(required));
  }

  function addShort(title, required) {
    form.addTextItem().setTitle(title).setRequired(Boolean(required));
  }

  function addMC(title, choices, includeOther, required) {
    const item = form.addMultipleChoiceItem().setTitle(title).setRequired(Boolean(required));
    const opts = choices.map((c) => item.createChoice(c));
    item.setChoices(opts);
    item.showOtherOption(Boolean(includeOther));
  }

  // Section 1
  addSection('1. Current Workflow and Timing');
  addMC('Do office staff process tickets as they arrive, at end-of-day, or both?', ['As they arrive', 'End-of-day batch', 'Both'], true, true);
  addShort('On a typical day, how many tickets are processed?', true);
  addParagraph('What are the top pain points right now (time, errors, missing tickets, duplicate entry, invoicing delays)?', false);

  // Section 2
  addSection('2. Ticket Formats and Variability');
  addShort('How many different ticket layouts exist today?', true);
  addMC('Are ticket templates stable, or do quarries/vendors change formats often?', ['Stable', 'Occasional changes', 'Frequent changes'], true, true);
  addParagraph('Which fields are always present vs sometimes missing?', false);
  addMC('Are there frequent low-quality images (blurry, angled, dark)?', ['Yes', 'No', 'Sometimes'], true, false);
  addMC('Are both front/back of tickets ever needed?', ['Yes', 'No', 'Sometimes'], true, false);
  addMC('Do they need to process multi-page ticket documents?', ['Yes', 'No', 'Not sure'], true, false);

  // Section 3
  addSection('3. Data Capture Rules');
  addParagraph('What exact fields must be captured from every ticket?', true);
  addParagraph('Should empty fields be allowed for specific columns (for example job number, plate, received by)?', false);
  addParagraph('What data validation rules should apply (numeric only, date format, allowed material types)?', true);
  addMC('Should net be auto-validated as gross minus tare, and what should happen on mismatch?', ['Yes - block until corrected', 'Yes - warn only', 'No validation needed'], true, true);
  addMC('How should duplicates be defined?', ['Ticket ID only', 'Ticket ID + Date', 'Ticket ID + Date + Quarry'], true, true);
  addMC('What should happen when a duplicate is detected?', ['Hard block', 'Warn and allow override', 'Auto-merge attempt'], true, true);

  // Section 4
  addSection('4. CSV and Spreadsheet Requirements');
  addParagraph('What columns must be in exported CSV in final production?', true);
  addParagraph('What column order is required?', false);
  addShort('What date format do they require in CSV? (example: YYYY-MM-DD)', false);
  addMC('Should numeric values include commas or plain digits?', ['Plain digits', 'Commas included', 'Depends by field'], true, false);
  addParagraph('Do they require any legacy column names that cannot change?', false);
  addParagraph('Where is CSV consumed next (person, system, accounting tool)?', false);
  addMC('Should CSV export be manual, scheduled, or both?', ['Manual', 'Scheduled', 'Both'], true, true);
  addShort('If scheduled, what times and timezone?', false);
  addMC('Do they want one CSV per day, per batch, or rolling append?', ['Per day', 'Per batch', 'Rolling append'], true, false);
  addMC('Do they need separate CSVs per quarry, project, or customer?', ['Yes', 'No', 'Maybe later'], true, false);

  // Section 5
  addSection('5. SharePoint and Microsoft 365');
  addParagraph('Where exactly are current spreadsheets stored in SharePoint (site, library, file)?', true);
  addMC('Should app write to SharePoint list, Excel table, or both?', ['SharePoint list', 'Excel table', 'Both'], true, true);
  addParagraph('Who owns SharePoint permissions and approvals internally?', false);
  addMC('Is Microsoft Entra login required for all users?', ['Yes', 'No', 'Not sure'], true, true);
  addMC('Do they want only users from a specific group/security role to access app?', ['Yes', 'No', 'Not sure'], true, false);
  addParagraph('Are there any restrictions on third-party cloud services (Google Vision, Azure AI, etc.)?', false);

  // Section 6
  addSection('6. Users and Permissions');
  addShort('How many active users will use this app in first 3 months?', true);
  addShort('How many users upload only vs review/approve?', false);
  addMC('Do they want different permission levels by account?', ['Yes', 'No', 'Not sure yet'], true, true);
  addParagraph('Minimum roles needed (for example uploader, reviewer, admin)?', false);

  // Section 7
  addSection('7. Review and Approval UX');
  addMC('Should every ticket require human confirmation initially?', ['Yes', 'No', 'Start with yes then revisit'], true, true);
  addParagraph('Which fields are considered critical and must always be reviewed?', true);
  addMC('Should app support optional keyboard shortcuts for faster review later?', ['Yes', 'No', 'Maybe later'], true, false);
  addMC('Should app support bulk approve for high-confidence records later?', ['Yes', 'No', 'Maybe later'], true, false);

  // Section 8
  addSection('8. OCR and Accuracy Expectations');
  addMC(
    'Are you comfortable with this rollout model: Phase 1 human confirm every ticket, Phase 2 optional strict auto-approve?',
    ['Yes', 'No', 'Need to discuss'],
    true,
    true
  );
  addMC(
    'For invoice safety, do you agree we should default low confidence tolerance and route uncertain records to manual review?',
    ['Yes', 'No', 'Need examples first'],
    true,
    true
  );
  addMC('Do you want raw OCR text kept for troubleshooting?', ['Yes', 'No', 'Only for failed tickets'], true, false);

  // Section 9
  addSection('9. Invoicing Requirements');
  addParagraph('Is there existing invoice numbering format to follow?', false);
  addMC('Should invoice output be PDF, spreadsheet output, or integration to accounting system?', ['PDF', 'Spreadsheet output', 'Accounting integration', 'Mixed'], true, true);
  addMC('Should invoices be grouped by customer/date/project?', ['Yes', 'No', 'Depends by client'], true, false);

  // Section 10
  addSection('10. On-Prem and Integration Constraints');
  addMC('Is on-prem CSV drop required in Phase 1, or acceptable as fallback if IT setup blocks timeline?', ['Required in Phase 1', 'Fallback acceptable if blocked', 'Phase 2 is fine'], true, true);
  addShort('Exact destination path for on-prem exports (if known now)?', false);
  addParagraph('Who can connect us with whoever manages that server path and permissions?', false);
  addMC('If export fails, should behavior be retry + alert + manual fallback?', ['Yes (all three)', 'Retry + alert only', 'Manual fallback only'], true, true);
  addShort('How long should exported files be retained?', false);

  // Section 11
  addSection('11. Operations, Support, and Audit');
  addParagraph('What audit details are required (who changed what and when)?', false);
  addShort('How long should ticket images and logs be retained?', false);
  addMC('Do they need a simple dashboard (queued, reviewed, approved, exported counts)?', ['Yes', 'No', 'Maybe later'], true, false);

  // Section 12
  addSection('12. Nice-to-Have Future Items');
  addMC('Auto-approve strict high-confidence tickets', ['Keep', 'Postpone', 'Remove'], true, false);
  addMC('Batch processing dashboard and SLA timers', ['Keep', 'Postpone', 'Remove'], true, false);
  addMC('Search and filter by ticket/customer/date', ['Keep', 'Postpone', 'Remove'], true, false);
  addMC('Reconciliation report (processed vs invoiced vs exported)', ['Keep', 'Postpone', 'Remove'], true, false);

  addParagraph('Anything else we should know before build starts?', false);

  Logger.log('EDIT URL: ' + form.getEditUrl());
  Logger.log('LIVE URL: ' + form.getPublishedUrl());
}
