function createUncleClarificationForm() {
  const form = FormApp.create('Uncle Clarification Question List - Office Ticket OCR App');

  form.setDescription(
    'Please answer these questions so we can finalize the office-side ticket OCR workflow.\n\n' +
    'Already Assumed:\n' +
    '- Current process is manual\n' +
    '- Tickets are handwritten\n' +
    '- Review happens on same screen as image preview\n' +
    '- Low-confidence fields should be highlighted\n' +
    '- Invoice work is in scope immediately\n' +
    '- On-prem export in Phase 1 preferred if feasible'
  );

  const sections = [
    {
      title: '1. Current Workflow and Timing',
      questions: [
        'Do office staff process tickets as they arrive, at end-of-day, or both?',
        'On a typical day, how many tickets are processed?',
        'What are the top pain points right now (time, errors, missing tickets, duplicate entry, invoicing delays)?'
      ]
    },
    {
      title: '2. Ticket Formats and Variability',
      questions: [
        'How many different ticket layouts exist today?',
        'Are ticket templates stable, or do quarries/vendors change formats often?',
        'Which fields are always present vs sometimes missing?',
        'Are there frequent low-quality images (blurry, angled, dark)?',
        'Are both front/back of tickets ever needed?',
        'Do they need to process multi-page ticket documents?'
      ]
    },
    {
      title: '3. Data Capture Rules',
      questions: [
        'What exact fields must be captured from every ticket?',
        'Should empty fields be allowed for specific columns (for example job number, plate, received by)?',
        'What data validation rules should apply (numeric only, date format, allowed material types)?',
        'Should net be auto-validated as gross minus tare, and what should happen on mismatch?',
        'How should duplicates be defined (ticket id only, ticket id plus date, ticket id plus quarry)?',
        'What should happen when a duplicate is detected?'
      ]
    },
    {
      title: '4. CSV and Spreadsheet Requirements',
      questions: [
        'What columns must be in exported CSV in final production?',
        'What column order is required?',
        'What date format do they require in CSV?',
        'Should numeric values include commas or plain digits?',
        'Do they require any legacy column names that cannot change?',
        'Where is CSV consumed next (person, system, accounting tool)?',
        'Should CSV export be manual, scheduled, or both?',
        'If scheduled, what times and timezone?',
        'Do they want one CSV per day, per batch, or rolling file append?',
        'Do they need separate CSVs per quarry, project, or customer?'
      ]
    },
    {
      title: '5. SharePoint and Microsoft 365',
      questions: [
        'Where exactly are current spreadsheets stored in SharePoint (site, library, file)?',
        'Should app write to SharePoint list, Excel table, or both?',
        'Who owns SharePoint permissions and approvals internally?',
        'Is Microsoft Entra login required for all users?',
        'Do they want only users from a specific group/security role to access app?',
        'Are there any restrictions on third-party cloud services (Google Vision, Azure AI, etc.)?'
      ]
    },
    {
      title: '6. Users and Permissions',
      questions: [
        'How many active users will use this app in first 3 months?',
        'How many users upload only vs review/approve?',
        'Do they want different permission levels by account?',
        'Minimum roles needed: uploader, reviewer, admin?'
      ]
    },
    {
      title: '7. Review and Approval UX',
      questions: [
        'Should every ticket require human confirmation initially?',
        'Which fields are considered critical and must always be reviewed?',
        'Should app support optional keyboard shortcuts for faster review later?',
        'Should app support bulk approve for high-confidence records later?'
      ]
    },
    {
      title: '8. OCR and Accuracy Expectations',
      questions: [
        'Are you comfortable with this rollout model: Phase 1 human confirm on every ticket, Phase 2 optional auto-approve only for strict pass rules?',
        'For invoice safety, do you agree we should default low confidence tolerance and route uncertain records to manual review?',
        'Do you want raw OCR text kept for troubleshooting, or only final confirmed ticket data?'
      ]
    },
    {
      title: '9. Invoicing Requirements',
      questions: [
        'Is there existing invoice numbering format to follow?',
        'Should invoice output be PDF, spreadsheet output, or integration to accounting system?',
        'Should invoices be grouped by customer/date/project?'
      ]
    },
    {
      title: '10. On-Prem and Integration Constraints',
      questions: [
        'Is on-prem CSV drop required in Phase 1, or acceptable as fallback if IT setup blocks timeline?',
        'Exact destination path for on-prem exports (if known now)?',
        'Who can connect us with whoever manages that server path and permissions?',
        'If export fails, should behavior be: retry plus alert plus manual fallback?',
        'How long should exported files be retained?'
      ]
    },
    {
      title: '11. Operations, Support, and Audit',
      questions: [
        'What audit details are required (who changed what and when)?',
        'How long should ticket images and logs be retained?',
        'Do they need a simple dashboard (queued, reviewed, approved, exported counts)?'
      ]
    },
    {
      title: '12. Nice-to-Have Future Items (Confirm Priority)',
      questions: [
        'Auto-approve strict high-confidence tickets: keep, postpone, or remove?',
        'Batch processing dashboard and SLA timers: keep, postpone, or remove?',
        'Search and filter by ticket/customer/date: keep, postpone, or remove?',
        'Reconciliation report (processed vs invoiced vs exported): keep, postpone, or remove?'
      ]
    }
  ];

  sections.forEach((section, idx) => {
    if (idx > 0) {
      form.addPageBreakItem().setTitle(section.title);
    } else {
      form.addSectionHeaderItem().setTitle(section.title);
    }

    section.questions.forEach((q) => {
      form.addParagraphTextItem().setTitle(q).setRequired(false);
    });
  });

  form.addParagraphTextItem()
    .setTitle('Anything else we should know before build starts?')
    .setRequired(false);

  Logger.log('EDIT URL: ' + form.getEditUrl());
  Logger.log('LIVE URL: ' + form.getPublishedUrl());
}
