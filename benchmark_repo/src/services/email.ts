import { db } from '../db';

interface EmailClient {
  send(options: { to: string; subject: string; body: string }): Promise<void>;
}

// Mock email client for demonstration
const emailClient: EmailClient = {
  async send(options) {
    // Simulate email sending that might fail
    if (Math.random() > 0.9) {
      throw new Error('Email service unavailable');
    }
  }
};

// VULNERABILITY: Unhandled promise rejection
export async function sendWelcomeEmail(userId: number) {
  const user = await db.users.findById(userId);

  // No error handling - if email fails, promise rejection is unhandled
  // This can crash the Node.js process
  await emailClient.send({
    to: user.email,
    subject: 'Welcome!',
    body: 'Thanks for signing up'
  });
}

// VULNERABILITY: Fire-and-forget async call
export function notifyUserAsync(userId: number, message: string) {
  // Promise is created but not awaited or caught
  // Errors will be silently swallowed or crash the process
  sendNotification(userId, message);
}

async function sendNotification(userId: number, message: string) {
  const user = await db.users.findById(userId);
  await emailClient.send({
    to: user.email,
    subject: 'Notification',
    body: message
  });
}
