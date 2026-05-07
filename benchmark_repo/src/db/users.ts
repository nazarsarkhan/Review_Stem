import { db } from './connection';

export async function getUserByName(name: string) {
    const result = await db.query(`SELECT * FROM users WHERE name = '${name}'`);
    return result[0];
}
