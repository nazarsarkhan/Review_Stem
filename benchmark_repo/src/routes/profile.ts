import express from 'express';

const router = express.Router();

// VULNERABILITY: XSS through unsanitized username parameter
router.get('/profile/:username', (req, res) => {
  const username = req.params.username;
  // Direct interpolation of user input into HTML without escaping
  res.send(`<html>
    <head><title>User Profile</title></head>
    <body>
      <h1>Profile: ${username}</h1>
      <p>Welcome to ${username}'s profile page!</p>
    </body>
  </html>`);
});

export default router;
