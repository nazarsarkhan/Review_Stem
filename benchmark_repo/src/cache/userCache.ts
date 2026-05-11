import { db } from '../db';
import { cache } from './redis';

export async function getUser(userId: string) {
    const cacheKey = `user:${userId}`;
    const cached = await cache.get(cacheKey);
    if (cached) return JSON.parse(cached);
    const user = await db.users.findById(userId);
    await cache.set(cacheKey, JSON.stringify(user));
    return user;
}

export async function updateUser(userId: string, data: any) {
    await db.users.update(userId, data);
}
