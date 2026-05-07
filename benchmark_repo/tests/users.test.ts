import { UserService } from '../src/services/userService';

describe('UserService', () => {
    it('should track user count', () => {
        const service = new UserService();
        service.addUser({ id: '1', name: 'Test' });
        expect((service as any).userMap.size).toBe(1);
    });
});
