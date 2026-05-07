import express from 'express';
const app = express();
app.use(express.json());

const db = {
    query: (text, params) => {
        console.log(`Executing: ${text}`);
        return Promise.resolve({ rows: [] });
    }
};

app.get('/health', (req, res) => {
    res.send({ status: 'ok' });
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
