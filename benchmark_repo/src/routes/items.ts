import express from 'express';
const router = express.Router();

router.get('/items', (req, res) => {
    const page = parseInt(req.query.page as string) || 1;
    const limit = parseInt(req.query.limit as string) || 10;
    const offset = page * limit; 
    
    res.json({ page, limit, offset });
});

export default router;
