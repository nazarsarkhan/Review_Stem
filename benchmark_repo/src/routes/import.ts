import express from 'express';
const router = express.Router();

router.post('/import', async (req, res) => {
    try {
        processLargeCSV(req.body.csv).catch(e => console.error(e));
        res.sendStatus(200);
    } catch (e) {
        res.status(500).json({ error: 'import failed' });
    }
});

async function processLargeCSV(csv: string) {
}

export default router;
