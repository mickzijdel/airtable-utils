---
name: airtable-scripting
description: "Comprehensive guidance for writing Airtable scripts in both Scripting Extensions (manual execution) and Automation Scripts (triggered execution). Use when writing scripts for Airtable Scripting Extensions, creating automation scripts, integrating external APIs with Airtable, working with Airtable's native Scripting API, handling different field types programmatically, or troubleshooting script errors."
---

# Airtable Scripting Skill

## Purpose

This skill provides comprehensive guidance for writing Airtable scripts in both **Scripting Extensions** (manual execution) and **Automation Scripts** (triggered execution). It covers the Airtable Scripting API, Web API integration, field handling, and best practices.

**Key conventions used throughout this skill:**
- **Always use IDs** (not names) to refer to tables, fields, views, and bases. IDs are stable; names can be renamed by users and break scripts silently.
- **`remoteFetchAsync`** is for Scripting Extensions only. **`fetch`** is for Automation Scripts only. Do not mix them up.

## Direct Airtable Access via MCP

If the user asks Claude to **directly read or modify Airtable data** (rather than write a script for them to run), use an Airtable MCP server instead of this skill:

```
/plugin install airtable@claude-plugins-official
```

Alternatively, the community [`airtable-mcp-server`](https://github.com/domdomegg/airtable-mcp-server) by domdomegg offers the same read/write + schema capabilities and can be run via `npx` or Docker.

This skill is for **authoring scripts** that users will paste into Airtable's Scripting Extension or Automation editor.

## When to Use This Skill

Use this skill when:
- Writing scripts for Airtable Scripting Extensions
- Creating automation scripts ("Run a script" action)
- Integrating external APIs with Airtable (`remoteFetchAsync` in Extensions, `fetch` in Automations)
- Working with Airtable's native Scripting API
- Handling different field types programmatically
- Troubleshooting script errors

## Table of Contents

1. [Scripting Extension vs Automation Scripts](#scripting-extension-vs-automation-scripts)
2. [Core Scripting API](#core-scripting-api)
3. [Web API Integration](#web-api-integration)
4. [Field Types & Formats](#field-types--formats)
5. [Input/Output APIs](#inputoutput-apis)
6. [Best Practices](#best-practices)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

---

## Scripting Extension vs Automation Scripts

### Key Differences

| Feature | Scripting Extension | Automation Script |
|---------|-------------------|-------------------|
| **Execution** | Manual (Run button) | Automatic (triggered) |
| **Location** | Runs in browser | Runs on Airtable servers |
| **Timeout** | No limit | 120 seconds (script), 30 seconds (fetch) |
| **Memory** | No limit | 512 MB |
| **Queries** | No limit | Max 30 `selectRecordsAsync` calls |
| **Fetch method** | `remoteFetchAsync()` | `fetch()` |
| **Fetch calls** | No limit | Max 50 `fetch` calls |
| **Mutations** | Rate limited | Max 15/second |
| **`input.config()`** | ✅ Interactive UI | ✅ Variables from triggers/actions |
| **`field.updateOptionsAsync()`** | ✅ Available | ❌ **NOT available** |
| **`output.set()`** | ✅ Available | ✅ Pass data to next step |
| **`output.markdown()`** | ✅ Rich output | ❌ Not available |
| **User interaction** | ✅ Via `input` API | ❌ No interaction |
| **CORS** | ⚠️ Limited (use `remoteFetchAsync`) | ✅ No CORS issues (use `fetch`) |

### When to Use Each

**Scripting Extension:**
- Manual data processing tasks
- Scripts requiring user input during execution
- Creating/updating single select options
- No timeout concerns
- Rich output formatting needed

**Automation Script:**
- Triggered workflows (record created, form submitted, scheduled)
- Background processing
- Integration with automation actions
- No user interaction required

---

## Core Scripting API

### Base & Table Operations

```javascript
// Access base (globally available)
const base = base;

// Get table by ID (PREFERRED - stable across renames)
const table = base.getTableById("tblXXXXXXXXXX");

// Get table by name (AVOID - breaks if table is renamed)
// const table = base.getTable("Table Name");

// Get all tables
const tables = base.tables;

// Get table metadata
console.log(table.name);        // Table name
console.log(table.id);          // tblXXXXXXXXXX
console.log(table.fields);      // Array of Field objects
console.log(table.views);       // Array of View objects
```

### Querying Records

```javascript
// Query all records from table
const query = await table.selectRecordsAsync();
const records = query.records;

// Query specific fields only (more efficient) - use field IDs
const query = await table.selectRecordsAsync({
    fields: ["fldXXXXXXXXXX", "fldYYYYYYYYYY"]
});

// Query from a view (inherits view filters/sorting) - use view ID
const view = table.getViewById("viwXXXXXXXXXX");
const query = await view.selectRecordsAsync();

// Access record data
for (let record of query.records) {
    const id = record.id;                    // recXXXXXXXXXX
    const name = record.name;                // Primary field value
    
    // Get cell values by field ID (PREFERRED)
    const value = record.getCellValue("fldXXXXXXXXXX");
    const stringValue = record.getCellValueAsString("fldXXXXXXXXXX");
    
    // Access all fields by ID
    const fields = record.getCellValuesByFieldId();
}
```

**Important:** `selectRecordsAsync` accepts field **names**, **IDs**, or **Field objects**. Always prefer IDs for stability:
```javascript
const query = await table.selectRecordsAsync({
    fields: [
        "fldXXXXXXXXXX",              // By ID (PREFERRED - stable)
        table.getFieldById("fldYYYYYYYYYY") // By Field object (also stable)
        // "Field Name",              // By name (AVOID - breaks on rename)
    ]
});
```

### Creating Records

```javascript
// Create single record (use field IDs as keys)
const recordId = await table.createRecordAsync({
    "fldXXXXXXXXXX": "Value",
    "fldYYYYYYYYYY": 42,
    "fldZZZZZZZZZZ": true
});

// Create multiple records (max 50 per call)
const recordIds = await table.createRecordsAsync([
    {
        fields: {
            "fldXXXXXXXXXX": "Record 1",
            "fldYYYYYYYYYY": 100
        }
    },
    {
        fields: {
            "fldXXXXXXXXXX": "Record 2",
            "fldYYYYYYYYYY": 200
        }
    }
]);

// Batching for >50 records
const recordsToCreate = [...]; // Your array of record objects

while (recordsToCreate.length > 0) {
    const batch = recordsToCreate.splice(0, 50);
    await table.createRecordsAsync(batch);
}
```

### Updating Records

```javascript
// Update single record
await table.updateRecordAsync(recordId, {
    "fldXXXXXXXXXX": "New Value"
});

// Update single record (alternative - pass record object)
await table.updateRecordAsync(record, {
    "fldXXXXXXXXXX": "New Value"
});

// Update multiple records (max 50 per call)
await table.updateRecordsAsync([
    {
        id: "recXXXXXXXXXX",
        fields: {
            "fldXXXXXXXXXX": "Updated"
        }
    },
    {
        id: "recYYYYYYYYYY",
        fields: {
            "fldXXXXXXXXXX": "Also Updated"
        }
    }
]);

// Batching pattern for updates
while (recordsToUpdate.length > 0) {
    await table.updateRecordsAsync(recordsToUpdate.slice(0, 50));
    recordsToUpdate = recordsToUpdate.slice(50);
}
```

### Deleting Records

```javascript
// Delete single record
await table.deleteRecordAsync(recordId);

// Delete multiple records (max 50 per call)
await table.deleteRecordsAsync([
    "recXXXXXXXXXX",
    "recYYYYYYYYYY"
]);

// Delete with batching
while (recordIds.length > 0) {
    await table.deleteRecordsAsync(recordIds.slice(0, 50));
    recordIds = recordIds.slice(50);
}
```

### Field Operations

```javascript
// Get field by ID (PREFERRED)
const field = table.getFieldById("fldXXXXXXXXXX");

// Get field by name (AVOID - breaks on rename)
// const field = table.getField("Field Name");

// Field metadata
console.log(field.id);          // fldXXXXXXXXXX
console.log(field.name);        // Field Name
console.log(field.type);        // singleSelect, multipleSelects, etc.
console.log(field.description); // Field description
console.log(field.options);     // For select fields, attachments, etc.

// Update single/multiple select options (EXTENSION ONLY)
const selectField = table.getFieldById("fldXXXXXXXXXX");
await selectField.updateOptionsAsync({
    choices: [
        ...selectField.options.choices,  // Keep existing
        { name: "New Option" },           // Add new
        { name: "Colored", color: "greenBright" }  // With color
    ]
});

// Available colors: blueBright, cyanBright, tealBright, greenBright, 
// yellowBright, orangeBright, redBright, pinkBright, purpleBright, 
// grayBright, blueDark, cyanDark, tealDark, greenDark, yellowDark, 
// orangeDark, redDark, pinkDark, purpleDark, grayDark
```

**Important:** `field.updateOptionsAsync()` is **ONLY available in Scripting Extensions**, NOT in Automation Scripts.

---

## Web API Integration

### Fetch Methods: Extension vs Automation

**Critical distinction:**
- **Scripting Extensions** run in the browser → use `remoteFetchAsync()` to bypass CORS
- **Automation Scripts** run on Airtable servers → use `fetch()` (no CORS issues, `remoteFetchAsync` is NOT available)

### Scripting Extension: remoteFetchAsync

```javascript
// Basic GET request (Extension only)
const response = await remoteFetchAsync('https://api.example.com/data');
const data = await response.json();

// POST request with headers (Extension only)
const response = await remoteFetchAsync('https://api.example.com/create', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        field1: 'value1',
        field2: 'value2'
    })
});

if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
}

const data = await response.json();
```

### Automation Script: fetch

```javascript
// Basic GET request (Automation only)
const response = await fetch('https://api.example.com/data');
const data = await response.json();

// POST request with headers (Automation only)
const response = await fetch('https://api.example.com/create', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        field1: 'value1',
        field2: 'value2'
    })
});

if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
}

const data = await response.json();
```

### Airtable Web API Examples

When calling the Airtable Web API from scripts, use the appropriate fetch method for your context.

**Extension example (remoteFetchAsync):**

```javascript
const baseId = 'appXXXXXXXXXXXX';
const tableId = 'tblXXXXXXXXXX';
const fieldId = 'fldXXXXXXXXXX';
const apiKey = 'patXXXXXXXXXXXXXX';  // Personal Access Token

// Create records via Web API (Extension)
const url = `https://api.airtable.com/v0/${baseId}/${tableId}`;

const response = await remoteFetchAsync(url, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        records: [
            {
                fields: {
                    [fieldId]: "Value"
                }
            }
        ],
        typecast: true  // Auto-create select options
    })
});

const data = await response.json();
console.log(data.records.map(r => r.id));
```

**Automation example (fetch):**

```javascript
const baseId = 'appXXXXXXXXXXXX';
const tableId = 'tblXXXXXXXXXX';
const fieldId = 'fldXXXXXXXXXX';
const apiKey = 'patXXXXXXXXXXXXXX';  // Personal Access Token

// Create records via Web API (Automation)
const url = `https://api.airtable.com/v0/${baseId}/${tableId}`;

const response = await fetch(url, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        records: [
            {
                fields: {
                    [fieldId]: "Value"
                }
            }
        ],
        typecast: true  // Auto-create select options
    })
});

const data = await response.json();
console.log(data.records.map(r => r.id));
```

**Why use Web API instead of Scripting API?**

- Creating single select options in automation scripts (use `typecast: true`)
- Accessing bases/tables outside the current base
- Bypassing automation script limitations (30 queries, 50 fetch calls)
- Working with synced tables (synced tables are read-only via Scripting API)

---

## Field Types & Formats

### Scripting API Format

```javascript
// Text (singleLineText)
{"fldTEXTXXXXXX": "Hello World"}

// Long text (multilineText) — plain string
{"fldLTXTXXXXXX": "Line one\nLine two"}

// Rich text (richText) — plain string on write; stored/returned as Markdown
{"fldRTXTXXXXXX": "**Bold** and _italic_"}

// Number
{"fldNUMXXXXXXX": 42}

// Checkbox
{"fldCHKXXXXXXX": true}

// Date (ISO 8601)
{"fldDATEXXXXXX": "2025-12-24"}

// Date & Time (ISO 8601 with timezone)
{"fldDTMXXXXXXX": "2025-12-24T14:30:00.000Z"}

// Single Select
{"fldSSELXXXXXX": {name: "In Progress"}}

// Multiple Select
{"fldMSELXXXXXX": [{name: "Important"}, {name: "Urgent"}]}

// Linked Records
{"fldLNKXXXXXXX": [{id: "recXXXXXXXXXX"}, {id: "recYYYYYYYYYY"}]}

// Attachments
{"fldATTXXXXXXX": [
    {
        url: "https://example.com/file.pdf",
        filename: "file.pdf"
    }
]}

// User (singleCollaborator)
{"fldUSRXXXXXXX": {id: "usrXXXXXXXXXX"}}

// Multiple Collaborators (array of users)
{"fldUSRSXXXXXX": [{id: "usrXXXXXXXXXX"}, {id: "usrYYYYYYYYYY"}]}

// Barcode (object: text is required, type is optional)
{"fldBARXXXXXXX": {text: "012345678905", type: "code128"}}

// Email
{"fldEMLXXXXXXX": "user@example.com"}

// URL
{"fldURLXXXXXXX": "https://example.com"}

// Phone
{"fldPHNXXXXXXX": "+1-555-0123"}

// Rating
{"fldRATXXXXXXX": 4}

// Duration (seconds)
{"fldDURXXXXXXX": 3600}

// Currency
{"fldCURXXXXXXX": 99.99}

// Percent
{"fldPCTXXXXXXX": 0.75}  // 75%

// Button (read-only)
// Cannot be set via API

// Formula (read-only)
// Cannot be set via API

// Rollup (read-only)
// Cannot be set via API

// Count (read-only)
// Cannot be set via API

// Lookup (read-only)
// Cannot be set via API

// Created Time (read-only)
// Cannot be set via API

// Last Modified Time (read-only)
// Cannot be set via API

// Created By (read-only)
// Cannot be set via API

// Last Modified By (read-only)
// Cannot be set via API

// Auto Number (read-only)
// Cannot be set via API

// AI Text (read-only) — value is AI-generated from a prompt
// Cannot be set via API

// External Sync Source (read-only) — synced single-select-like value
// Cannot be set via API
```

### Web API Format with typecast

When using `typecast: true`, field values can be strings that Airtable converts:

```javascript
{
    "typecast": true,
    "records": [{
        "fields": {
            "fldSSELXXXXXX": "Option Name",     // String → creates option
            "fldMSELXXXXXX": ["A", "B"],         // Array → creates options
            "fldNUMXXXXXXX": "42",               // String → number
            "fldCHKXXXXXXX": "true",             // String → boolean
            "fldLNKXXXXXXX": ["RecordName1"]     // String → finds record
        }
    }]
}
```

### Reading Field Values

```javascript
// Get raw value (use field ID)
const value = record.getCellValue("fldXXXXXXXXXX");

// Get string representation
const stringValue = record.getCellValueAsString("fldXXXXXXXXXX");

// Handle null values
const status = record.getCellValue("fldSSELXXXXXX")?.name || "No Status";

// Handle arrays (Multiple Select, Linked Records, etc.)
const tags = record.getCellValue("fldMSELXXXXXX") || [];
const tagNames = tags.map(tag => tag.name);

// Handle attachments
const attachments = record.getCellValue("fldATTXXXXXXX") || [];
const urls = attachments.map(att => att.url);
```

---

## Input/Output APIs

### Scripting Extension Input

```javascript
// Configuration dialog
const config = input.config({
    title: "Script Configuration",
    description: "Configure the script parameters",
    items: [
        input.config.table("sourceTable", {
            label: "Source Table",
            description: "Select the table to process"
        }),
        input.config.field("statusField", {
            label: "Status Field",
            parentTable: "sourceTable"
        }),
        input.config.select("action", {
            label: "Action",
            options: [
                {label: "Create", value: "create"},
                {label: "Update", value: "update"}
            ]
        }),
        input.config.text("searchTerm", {
            label: "Search Term"
        })
    ]
});

// Access configured values
// input.config.table() returns a Table object directly — do NOT re-fetch:
// ❌ const sourceTable = base.getTable(config.sourceTable); // Redundant!
// ✅ Just use it directly:
const sourceTable = config.sourceTable;
const statusField = config.statusField;

// ⚠️ CRITICAL GOTCHA: config Field objects as object keys
//
// input.config.field() returns a Field object. This works fine as an
// ARGUMENT to getCellValue(), getCellValueAsString(), selectRecordsAsync():
//   record.getCellValue(config.statusField)              // ✅ Works
//   table.selectRecordsAsync({ fields: [config.statusField] }) // ✅ Works
//
// But when used as a COMPUTED PROPERTY KEY in an object literal,
// JavaScript calls .toString() on it → "[object Object]" → silent breakage:
//   { [config.statusField]: "Done" }  // ❌ Key becomes "[object Object]"
//
// Fix: extract .id from each field for use as object keys.
// Best practice: do this once at the top of your script.
const F = {
    status: config.statusField.id,
    // ... all other config fields
};
// Then use F.status as keys:
//   { [F.status]: { name: "Done" } }  // ✅ Key is "fldXXXXXXXXXX"

// Button selection
const choice = await input.buttonsAsync(
    "Do you want to continue?",
    ["Yes", "No"]
);

if (choice === "Yes") {
    // Proceed
}

// Text input
const name = await input.textAsync("Enter a name:");

// Table selection
const table = await input.tableAsync("Select a table:");

// Field selection
const field = await input.fieldAsync("Select a field:", table);

// Record selection
const record = await input.recordAsync("Select a record:", table);

// File import (CSV, JSON, etc.)
const file = await input.fileAsync(
    "Upload a file",
    { allowedFileTypes: ['.csv', 'text/csv'] }
);
// file.parsedContents is auto-parsed by Airtable.
//
// ⚠️ CRITICAL GOTCHA: Auto-parsed CSV values are NOT always strings.
// Airtable may parse "42" → number 42, "true" → boolean true, "" → null.
// Calling .trim(), .substring(), .toLowerCase() etc. on these will throw:
//   TypeError: (row[i] || "").trim is not a function
//
// Fix: normalize ALL cells to strings immediately after parsing:
let rows = file.parsedContents;
for (let r = 0; r < rows.length; r++) {
    for (let c = 0; c < rows[r].length; c++) {
        rows[r][c] = String(rows[r][c] ?? '');
    }
}
// Now all downstream code can safely call string methods on any cell.
```

### Automation Script Input

```javascript
// Access trigger/action variables
const config = input.config();

// Example: From "When record created" trigger
const recordId = config.recordId;

// Example: From previous action
const previousOutput = config.variableName;

// No interactive input allowed in automation scripts
```

### Scripting Extension Output

```javascript
// Text output
output.text("Processing complete!");

// Markdown output
output.markdown(`
# Results

- Processed: ${count} records
- Status: ✅ Success
`);

// Clear output
output.clear();

// Inspect (debug)
output.inspect({
    recordCount: count,
    errors: errorList
});

// Table
output.table([
    {name: "Alice", age: 30},
    {name: "Bob", age: 25}
]);
```

### Automation Script Output

```javascript
// Set output variables for next action
output.set("recordIds", recordIds);
output.set("count", processedCount);
output.set("result", {
    success: true,
    message: "Done"
});

// Access in next action via input.config()
```

---

## Best Practices

### Performance

```javascript
// ✅ Query specific fields only (by ID)
const query = await table.selectRecordsAsync({
    fields: ["fldNAMEXXXXXX", "fldSTATXXXXXX"]
});

// ❌ Query all fields unnecessarily
const query = await table.selectRecordsAsync();

// ✅ Use views for filtering (by ID)
const view = table.getViewById("viwXXXXXXXXXX");
const query = await view.selectRecordsAsync();

// ❌ Query all records then filter in script
const query = await table.selectRecordsAsync();
const active = query.records.filter(r => r.getCellValue("fldACTVXXXXXX"));
```

### Batching

```javascript
// ✅ Batch operations
async function batchOperation(operation, table, items, batchSize = 50) {
    while (items.length > 0) {
        const batch = items.splice(0, batchSize);
        
        if (operation === 'create') {
            await table.createRecordsAsync(batch);
        } else if (operation === 'update') {
            await table.updateRecordsAsync(batch);
        } else if (operation === 'delete') {
            await table.deleteRecordsAsync(batch);
        }
    }
}

// Usage
await batchOperation('create', table, recordsToCreate);
```

### Error Handling

```javascript
// ✅ Handle errors gracefully
// Use remoteFetchAsync (Extension) or fetch (Automation)
try {
    const response = await fetch(url);  // or remoteFetchAsync in Extensions
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    // Process data
    
} catch (error) {
    console.error("Error:", error.message);
    output.text(`❌ Error: ${error.message}`);
}

// ✅ Validate field values
const status = record.getCellValue("fldSTATXXXXXX");
if (!status) {
    console.warn(`Record ${record.id} has no status`);
    continue;
}

// ✅ Check for null before accessing properties
const assignee = record.getCellValue("fldASGNXXXXXX");
const email = assignee?.email || "unassigned@example.com";
```

### Code Organization

```javascript
// ✅ Use constants for field/table IDs at the top of your script
const TABLE_ID = "tblXXXXXXXXXX";
const STATUS_FIELD_ID = "fldSTATXXXXXX";
const NAME_FIELD_ID = "fldNAMEXXXXXX";
const STATUS_COMPLETE = "Complete";
const BATCH_SIZE = 50;

// ✅ Use functions for reusability
async function getRecordsByStatus(table, statusFieldId, statusValue) {
    const query = await table.selectRecordsAsync({
        fields: [statusFieldId]
    });
    
    return query.records.filter(record => {
        const status = record.getCellValue(statusFieldId);
        return status?.name === statusValue;
    });
}

// ✅ Add descriptive logging
console.log(`Processing ${records.length} records...`);
console.log(`Found ${matches.length} matching records`);
output.text(`✅ Updated ${updateCount} records`);
```

---

## Common Patterns

### Pattern 1: Bulk Update Based on Criteria

```javascript
async function bulkUpdateByStatus(table, statusFieldId, targetStatus, updates) {
    const query = await table.selectRecordsAsync({
        fields: [statusFieldId]
    });
    
    const recordsToUpdate = [];
    
    for (let record of query.records) {
        const status = record.getCellValue(statusFieldId);
        
        if (status?.name === targetStatus) {
            recordsToUpdate.push({
                id: record.id,
                fields: updates
            });
        }
    }
    
    if (recordsToUpdate.length > 0) {
        await batchOperation('update', table, recordsToUpdate);
        output.text(`✅ Updated ${recordsToUpdate.length} records`);
    } else {
        output.text('No records to update');
    }
}
```

### Pattern 2: Sync Between Tables

```javascript
async function syncTables(sourceTable, targetTable, mapping) {
    // mapping should contain field IDs, e.g.:
    // { linkFieldId: "fldLNK...", sourceNameFieldId: "fldNAM...", sourceStatusFieldId: "fldSTA...",
    //   targetNameFieldId: "fldNAM...", targetStatusFieldId: "fldSTA..." }

    // Query source
    const sourceQuery = await sourceTable.selectRecordsAsync({
        fields: [mapping.sourceNameFieldId, mapping.sourceStatusFieldId]
    });
    
    // Query target
    const targetQuery = await targetTable.selectRecordsAsync({
        fields: [mapping.linkFieldId]
    });
    const existingIds = new Set(
        targetQuery.records.map(r => r.getCellValue(mapping.linkFieldId)?.id)
    );
    
    // Find new records
    const newRecords = sourceQuery.records
        .filter(r => !existingIds.has(r.id))
        .map(r => ({
            fields: {
                [mapping.targetNameFieldId]: r.getCellValue(mapping.sourceNameFieldId),
                [mapping.targetStatusFieldId]: r.getCellValue(mapping.sourceStatusFieldId)
            }
        }));
    
    // Create new records
    if (newRecords.length > 0) {
        await batchOperation('create', targetTable, newRecords);
        output.text(`✅ Synced ${newRecords.length} new records`);
    } else {
        output.text('✅ No new records to sync');
    }
}
```

### Pattern 3: Find & Replace

```javascript
async function findAndReplace(table, fieldId, searchText, replaceText) {
    const query = await table.selectRecordsAsync({
        fields: [fieldId]
    });
    
    const updates = [];
    
    for (let record of query.records) {
        const value = record.getCellValueAsString(fieldId);
        
        if (value && value.includes(searchText)) {
            updates.push({
                id: record.id,
                fields: {
                    [fieldId]: value.replace(
                        new RegExp(searchText, 'g'),
                        replaceText
                    )
                }
            });
        }
    }
    
    if (updates.length > 0) {
        await batchOperation('update', table, updates);
        output.text(`✅ Updated ${updates.length} records`);
    } else {
        output.text('No matches found');
    }
}
```

### Pattern 4: Deduplicate Records

```javascript
async function deduplicateRecords(table, uniqueFieldId) {
    const query = await table.selectRecordsAsync({
        fields: [uniqueFieldId]
    });
    
    const seen = new Map();  // value → first record ID
    const duplicates = [];
    
    for (let record of query.records) {
        const value = record.getCellValueAsString(uniqueFieldId);
        
        if (!value) continue;
        
        if (seen.has(value)) {
            duplicates.push(record.id);
        } else {
            seen.set(value, record.id);
        }
    }
    
    if (duplicates.length > 0) {
        const confirm = await input.buttonsAsync(
            `Found ${duplicates.length} duplicates. Delete?`,
            ['Yes', 'No']
        );
        
        if (confirm === 'Yes') {
            await batchOperation('delete', table, duplicates);
            output.text(`✅ Deleted ${duplicates.length} duplicates`);
        }
    } else {
        output.text('✅ No duplicates found');
    }
}
```

### Pattern 5: CSV Import with Config Fields and Upsert

A common pattern for importing CSV data via a Scripting Extension: use `input.config`
for stable table/field references, extract field IDs for object keys, parse the CSV
with type coercion, and upsert records (create or update based on a match key).

```javascript
// ── 1. Config: tables and fields selected in the sidebar ──
const config = input.config({
    title: "CSV Importer",
    items: [
        input.config.table("myTable",    { label: "Target Table" }),
        input.config.field("fName",      { label: "Name field",  parentTable: "myTable" }),
        input.config.field("fEmail",     { label: "Email field", parentTable: "myTable" }),
        input.config.field("fStatus",    { label: "Status field (single select)", parentTable: "myTable" }),
    ]
});

// ── 2. Extract field IDs for use as object keys ──
// config.fName is a Field object → works in getCellValue() but NOT as { [config.fName]: val }
const F = {
    name:   config.fName.id,
    email:  config.fEmail.id,
    status: config.fStatus.id,
};
const table = config.myTable;  // Already a Table object, no need for base.getTable()

// ── 3. Import and normalize CSV ──
const file = await input.fileAsync("Upload CSV", { allowedFileTypes: ['.csv'] });
let rows = file.parsedContents;

// Coerce all cells to strings (Airtable auto-parses numbers/booleans/nulls)
for (let r = 0; r < rows.length; r++) {
    for (let c = 0; c < rows[r].length; c++) {
        rows[r][c] = String(rows[r][c] ?? '');
    }
}

const headers = rows[0];
const dataRows = rows.slice(1);

// ── 4. Build lookup index from existing records ──
const query = await table.selectRecordsAsync({ fields: [F.email, F.name, F.status] });
const emailToRecord = new Map();
for (const rec of query.records) {
    const email = (rec.getCellValueAsString(F.email) || '').trim().toLowerCase();
    if (email) emailToRecord.set(email, rec);
}

// ── 5. Upsert: update existing or create new ──
const creates = [];
const updates = [];

for (const row of dataRows) {
    const email = row[0].trim().toLowerCase();
    const name  = row[1].trim();
    if (!email) continue;

    const existing = emailToRecord.get(email);
    if (existing) {
        updates.push({
            id: existing.id,
            fields: { [F.name]: name, [F.status]: { name: "Updated" } }
        });
    } else {
        creates.push({
            fields: { [F.email]: email, [F.name]: name, [F.status]: { name: "New" } }
        });
    }
}

// ── 6. Batch write (max 50 per call) ──
while (creates.length > 0) await table.createRecordsAsync(creates.splice(0, 50));
while (updates.length > 0) { await table.updateRecordsAsync(updates.splice(0, 50)); }

output.markdown(`✅ Created ${creates.length}, updated ${updates.length}`);
```

---

## Troubleshooting

### Common Errors & Solutions

#### "Cannot update field config from scripting automation"

**Cause:** Trying to use `field.updateOptionsAsync()` in automation script

**Solution:** 
- Move to Scripting Extension, OR
- Use "Update Record" action to create new options, OR
- Call Web API with `typecast=true`

```javascript
// ❌ In Automation
await field.updateOptionsAsync({...});  // Error!

// ✅ Alternative: Use Web API (with fetch in Automation)
const url = `https://api.airtable.com/v0/${baseId}/${tableId}?typecast=true`;
await fetch(url, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        records: [{
            fields: {
                [singleSelectFieldId]: "New Option"  // Auto-creates
            }
        }]
    })
});
```

#### "Invalid arguments passed to output.set(key, value)"

**Cause:** Trying to pass non-JSON-serializable value (like Record objects)

**Solution:** Extract primitive values

```javascript
// ❌ Wrong
output.set('records', query.records);

// ✅ Correct
output.set('recordIds', query.records.map(r => r.id));
output.set('recordData', query.records.map(r => ({
    id: r.id,
    name: r.name,
    email: r.getCellValue('fldEMLXXXXXXX')
})));
```

#### "Cannot parse value for field X"

**Cause:** Field value format doesn't match field type

**Solution:** Check field type and use correct format

```javascript
// ❌ Wrong: Single select as string without typecast
{[fieldId]: "Option Name"}

// ✅ Correct: Single select as object
{[fieldId]: {name: "Option Name"}}

// ✅ Or use typecast in Web API
const url = `${baseUrl}?typecast=true`;
{[fieldId]: "Option Name"}  // Works with typecast
```

#### "undefined is not an object (evaluating 'record.getCellValue(...).name')"

**Cause:** Field is null/empty

**Solution:** Check for null before accessing properties

```javascript
// ❌ Wrong
const status = record.getCellValue("fldSTATXXXXXX").name;

// ✅ Correct
const statusObj = record.getCellValue("fldSTATXXXXXX");
const status = statusObj ? statusObj.name : "No Status";

// ✅ Or use optional chaining
const status = record.getCellValue("fldSTATXXXXXX")?.name || "No Status";
```

#### "Record ID recXXX does not exist"

**Cause:** Using synced table record ID in source base API call

**Solution:** Use source base record IDs, not synced table IDs

```javascript
// When creating records via API, capture returned IDs
// Use remoteFetchAsync (Extension) or fetch (Automation)
const response = await fetch(url, {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({records: [...]})
});

const data = await response.json();
const sourceRecordIds = data.records.map(r => r.id);

// Use these IDs for future operations in source base
```

#### Script timeout in Automation

**Cause:** Script exceeds 120 second limit

**Solution:** Split into multiple script actions

```javascript
// Split work across multiple scripts
// Script 1:
const records = await table.selectRecordsAsync();
output.set('total', records.records.length);
output.set('batch1', records.records.slice(0, 100).map(r => r.id));

// Script 2 (separate action):
const batch1Ids = input.config().batch1;
// Process batch1...

// Script 3 (separate action):
// Process batch2...
```

#### CORS errors with fetch() in Scripting Extensions

**Cause:** Using `fetch()` in a Scripting Extension (browser environment has CORS restrictions)

**Solution:** Use `remoteFetchAsync()` in Extensions. In Automation Scripts, `fetch()` works fine (no CORS).

```javascript
// ❌ Wrong in Scripting Extension - CORS error
const response = await fetch('https://api.example.com/data');

// ✅ Correct in Scripting Extension
const response = await remoteFetchAsync('https://api.example.com/data');

// ✅ Correct in Automation Script (fetch is the right method here)
const response = await fetch('https://api.example.com/data');
```

#### "Field '[object Object]' does not exist in table 'X'"

**Cause:** Using an `input.config.field()` Field object as a computed property key in an object literal. JavaScript calls `.toString()` on it → `"[object Object]"`.

This is a **very common mistake** in Scripting Extensions. `input.config.table()` returns a Table object and `input.config.field()` returns a Field object. These objects work fine as arguments to API methods (`getCellValue`, `selectRecordsAsync`), but fail silently as object keys.

**Solution:** Extract `.id` from each config field at the top of your script and use those string IDs as keys.

```javascript
// ❌ Wrong — Field object as key stringifies to "[object Object]"
await table.createRecordAsync({
    [config.fName]: "Alice",      // Key becomes "[object Object]"!
    [config.fEmail]: "a@b.com",   // Same problem
});

// ❌ Also wrong — base.getTable() on something that's already a Table
const table = base.getTable(config.myTable);  // Redundant, may error

// ✅ Correct — extract .id for keys, use config tables directly
const table = config.myTable;  // Already a Table object
const F = {
    name:  config.fName.id,   // String like "fldXXXXXXXXXX"
    email: config.fEmail.id,
};
await table.createRecordAsync({
    [F.name]: "Alice",        // Key is "fldXXXXXXXXXX" ✅
    [F.email]: "a@b.com",
});

// Note: Field objects still work fine as ARGUMENTS (not keys):
record.getCellValue(config.fName);                          // ✅
table.selectRecordsAsync({ fields: [config.fName] });       // ✅
```

#### "X is not a function" on CSV/file cell values (e.g. `.trim`, `.substring`, `.toLowerCase`)

**Cause:** `input.fileAsync()` auto-parses CSV contents. Cells that look like numbers become actual numbers, `"true"`/`"false"` become booleans, and empty cells may become `null`. Calling string methods on these non-string values throws a TypeError.

**Solution:** Normalize all cells to strings immediately after parsing, before any processing.

```javascript
const file = await input.fileAsync("Upload CSV", { allowedFileTypes: ['.csv'] });
let rows = file.parsedContents;

// ❌ This will throw on numeric/boolean/null cells:
const name = rows[1][0].trim();  // TypeError if cell is a number

// ✅ Normalize first:
for (let r = 0; r < rows.length; r++) {
    for (let c = 0; c < rows[r].length; c++) {
        rows[r][c] = String(rows[r][c] ?? '');
    }
}
// Now safe:
const name = rows[1][0].trim();  // Always a string ✅
```

---

## Quick Reference Card

### Essential Operations

```javascript
// Tables & Queries (always use IDs)
const table = base.getTableById("tblXXXXXXXXXX");
const query = await table.selectRecordsAsync({fields: ["fldXXXXXXXXXX"]});
const view = table.getViewById("viwXXXXXXXXXX");
const viewQuery = await view.selectRecordsAsync();

// CRUD
await table.createRecordsAsync([{fields: {...}}]);
await table.updateRecordsAsync([{id: "recXXX", fields: {...}}]);
await table.deleteRecordsAsync(["recXXX", "recYYY"]);

// Fields
const field = table.getFieldById("fldXXXXXXXXXX");
await field.updateOptionsAsync({choices: [...]});  // Extension only

// External API
// Extension: const response = await remoteFetchAsync(url, {method, headers, body});
// Automation: const response = await fetch(url, {method, headers, body});
const data = await response.json();

// Input/Output (Extension)
const config = input.config({title, items: [...]});
const choice = await input.buttonsAsync("Question", ["A", "B"]);
output.markdown("# Result");

// Input/Output (Automation)
const config = input.config();
output.set("key", value);
```

### Field Type Formats

```javascript
// Scripting API (use field IDs as keys)
{
    "fldTEXTXXXXXX": "string",
    "fldNUMXXXXXXX": 42,
    "fldCHKXXXXXXX": true,
    "fldDATEXXXXXX": "2025-12-24",
    "fldSSELXXXXXX": {name: "Option"},
    "fldMSELXXXXXX": [{name: "A"}, {name: "B"}],
    "fldLNKXXXXXXX": [{id: "recXXX"}]
}

// Web API with typecast=true (field IDs or names accepted)
{
    "fldSSELXXXXXX": "Option",        // String → creates option
    "fldMSELXXXXXX": ["A", "B"],      // Array → creates options
    "fldNUMXXXXXXX": "42"             // String → number
}
```

---

## Additional Resources

- [Airtable Scripting Documentation](https://airtable.com/developers/scripting)
- [Airtable Web API Documentation](https://airtable.com/developers/web/api/introduction)
- [Airtable Community Forums](https://community.airtable.com)

---

*Last updated: February 2026*
