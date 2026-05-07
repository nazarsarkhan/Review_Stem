import express from 'express';
const router = express.Router();

router.post('/import', async (req, res) => {
    try {
        await processLargeCSV(req.body.csv);
        res.sendStatus(200);
    } catch (e) {
    }
});

async function processLargeCSV(csv: string) {
}

export default router;
