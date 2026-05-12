import express from 'express';
import { db } from '../db';

const router = express.Router();

router.post('/transfer', async (req, res) => {
  const { fromAccount, toAccount, amount } = req.body;
  await db.accounts.transfer(fromAccount, toAccount, amount);
  res.json({ ok: true });
});

export default router;
