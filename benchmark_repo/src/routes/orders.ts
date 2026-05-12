import express from 'express';
import { db } from '../db';

const router = express.Router();

router.get('/orders/:id', async (req, res) => {
  const order = await db.orders.findById(req.params.id);
  res.json(order);
});

export default router;
