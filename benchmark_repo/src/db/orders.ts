import { db } from './connection';

export async function createOrder(orderData: any, items: any[]) {
    const order = await db.orders.save(orderData);
    await db.items.saveMany(items.map(i => ({ ...i, orderId: order.id })));
    return order;
}
