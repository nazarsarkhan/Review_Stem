import express from 'express';
const router = express.Router();

router.get('/stats', (req, res) => {
    res.json({ totalUsers: 1000, revenue: 50000 });
});

export default router;
