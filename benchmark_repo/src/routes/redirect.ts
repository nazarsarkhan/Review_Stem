import express from 'express';

const router = express.Router();

router.get('/go', (req, res) => {
  const next = String(req.query.next || '/');
  res.redirect(next);
});

export default router;
