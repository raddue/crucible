# Debug Transcript: Feedback Form 500 Errors on Special Characters

## User's Problem
Users get 500 errors when submitting the feedback form with special characters (single quotes, ampersands) in the comment field.

## Investigation

Looking at the error and code, the issue is clear. The error message:

```
Error: ER_PARSE_ERROR: You have an error in your SQL syntax; check the manual near ''s a great product' at line 1
```

And the code in `src/routes/feedback.js`:

```javascript
const query = `INSERT INTO feedback (name, email, comment) VALUES ('${name}', '${email}', '${comment}')`;
await db.query(query);
```

The code is using string interpolation to build the SQL query. When a user types something like "It's a great product", the resulting SQL becomes:

```sql
INSERT INTO feedback (name, email, comment) VALUES ('John', 'john@example.com', 'It's a great product')
```

The single quote in "It's" terminates the SQL string literal early, causing a parse error. The same issue would occur with other SQL-special characters.

**This is a SQL injection vulnerability**, not just an encoding bug. A malicious user could craft input that executes arbitrary SQL commands against your database. For example, a comment like `'); DROP TABLE feedback; --` would be catastrophic.

## Root Cause

String interpolation is used to embed user-provided values directly into SQL queries without any parameterization or escaping. This breaks SQL syntax when inputs contain quote characters and also opens a critical SQL injection attack vector.

## Fix

Replace the string interpolation with parameterized queries. The `mysql` library supports this natively:

```javascript
// src/routes/feedback.js
router.post('/feedback', async (req, res) => {
  const { name, email, comment } = req.body;
  const query = 'INSERT INTO feedback (name, email, comment) VALUES (?, ?, ?)';
  await db.query(query, [name, email, comment]);
  res.json({ success: true });
});
```

The `db.query` wrapper in `src/db/connection.js` also needs to accept parameters:

```javascript
// src/db/connection.js
const mysql = require('mysql');
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASS,
  database: 'app_db'
});
module.exports = { query: (sql, params) => pool.query(sql, params) };
```

With parameterized queries, the database driver handles escaping properly. The user's input is never interpolated into the SQL string -- it's sent as separate data to the database engine, which eliminates both the syntax error and the SQL injection vulnerability.

## Additional Recommendations

1. **Input validation**: Add server-side validation for the feedback fields (length limits, required fields).
2. **Error handling**: The route has no try/catch -- a database error will crash the request handler. Wrap it:
   ```javascript
   router.post('/feedback', async (req, res) => {
     try {
       const { name, email, comment } = req.body;
       const query = 'INSERT INTO feedback (name, email, comment) VALUES (?, ?, ?)';
       await db.query(query, [name, email, comment]);
       res.json({ success: true });
     } catch (err) {
       console.error('Feedback submission failed:', err);
       res.status(500).json({ success: false, error: 'Failed to submit feedback' });
     }
   });
   ```
3. **Audit other queries**: If this pattern exists here, it likely exists in other routes. Search the codebase for template literal SQL queries and fix them all.

## Why Not String Escaping?

You might be tempted to use `mysql.escape()` or manual escaping. Don't. Parameterized queries are the industry-standard solution because:
- They separate SQL logic from data at the protocol level
- They're immune to novel escaping bypasses
- They're easier to read and maintain
- They're recommended by OWASP as the primary defense against SQL injection
