import express from 'express';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import { db } from '../db';

const router = express.Router();
const SECRET = process.env.JWT_SECRET || 'default-secret';

// Security-critical endpoint without tests
router.post('/login', async (req, res) => {
  const { email, password } = req.body;

  // Input validation
  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  // Find user
  const user = await db.users.findByEmail(email);
  if (!user) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  // Verify password
  const valid = await bcrypt.compare(password, user.passwordHash);
  if (!valid) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  // Generate token
  const token = jwt.sign(
    { userId: user.id, email: user.email },
    SECRET,
    { expiresIn: '24h' }
  );

  res.json({ token, user: { id: user.id, email: user.email, name: user.name } });
});

// Password reset endpoint - also untested
router.post('/reset-password', async (req, res) => {
  const { email, resetToken, newPassword } = req.body;

  if (!email || !resetToken || !newPassword) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  const user = await db.users.findByEmail(email);
  if (!user || user.resetToken !== resetToken) {
    return res.status(401).json({ error: 'Invalid reset token' });
  }

  // Check token expiry
  if (user.resetTokenExpiry < Date.now()) {
    return res.status(401).json({ error: 'Reset token expired' });
  }

  // Hash new password
  const passwordHash = await bcrypt.hash(newPassword, 10);
  await db.users.update(user.id, { passwordHash, resetToken: null, resetTokenExpiry: null });

  res.json({ success: true });
});

export default router;
