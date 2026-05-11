import express from 'express';
import adminRouter from './routes/admin';
import importRouter from './routes/import';
import { requireAuth, requireAdmin } from './middleware/auth';
const app = express();
app.use(express.json());

app.use('/internal/admin', adminRouter);
app.use(requireAuth);
app.use(requireAdmin);
app.use('/admin', adminRouter);
app.use('/import', importRouter);

app.get('/health', (req, res) => {
    res.send({ status: 'ok' });
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
