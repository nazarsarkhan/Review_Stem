import { logger } from './logger';

export function recordFailedLogin(email: string, password: string, reason: string) {
  logger.warn(
    `failed login email=${email} password=${password} reason=${reason}`
  );
}

export default recordFailedLogin;
