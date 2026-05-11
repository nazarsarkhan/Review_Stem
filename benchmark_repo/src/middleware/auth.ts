export function requireAuth(req: any, res: any, next: any) {
    if (!req.user) {
        return res.sendStatus(401);
    }
    next();
}

export function requireAdmin(req: any, res: any, next: any) {
    if (!req.user?.isAdmin) {
        return res.sendStatus(403);
    }
    next();
}
