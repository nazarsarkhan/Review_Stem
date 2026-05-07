import { db } from '../db';
import { cache } from './redis';

export async function updateUser(userId: string, data: any) {
    await db.users.update(userId, data);
}
