import express from 'express';
import { db } from '../db';
import { verifyPassword } from '../services/passwords';

const router = express.Router();

router.post('/login', async (req, res) => {
  const user = await db.users.findByEmail(req.body.email);
  if (!user || !(await verifyPassword(req.body.password, user.passwordHash))) {
    return res.status(401).end();
  }
  res.json({ token: 'issued' });
});
