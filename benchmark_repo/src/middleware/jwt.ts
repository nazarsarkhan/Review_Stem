import jwt from 'jsonwebtoken';
import { Request, Response, NextFunction } from 'express';

export function authenticate(req: Request, res: Response, next: NextFunction) {
  const header = req.headers.authorization || '';
  const token = header.replace(/^Bearer\s+/, '');
  const claims = jwt.decode(token) as { sub: string } | null;
  if (!claims) return res.status(401).end();
  (req as any).userId = claims.sub;
  next();
}
