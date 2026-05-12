import express from 'express';
import pug from 'pug';

const router = express.Router();

router.post('/render', (req, res) => {
  const template = String(req.body.template || '');
  res.send(pug.compile(template)({}));
});

export default router;
