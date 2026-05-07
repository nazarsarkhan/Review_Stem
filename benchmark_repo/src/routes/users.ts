import express from 'express';
const router = express.Router();

router.get('/user', (req, res) => {
    res.json({ id: '1', fullName: 'John Doe' });
});

export default router;
