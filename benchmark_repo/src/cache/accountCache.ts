import { db } from '../db';
import { cache } from './redis';

export async function getAccount(accountId: string) {
    const cacheKey = `account:${accountId}`;
    const cached = await cache.get(cacheKey);
    if (cached) return JSON.parse(cached);
    const account = await db.users.findById(accountId);
    await cache.set(cacheKey, JSON.stringify(account));
    return account;
}

export async function updateAccount(accountId: string, data: any) {
    await db.users.update(accountId, data);
    await cache.del(`accounts:${accountId}`);
}
