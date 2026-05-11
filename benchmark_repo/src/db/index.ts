export const db = {
    users: {
        async findById(userId: string) {
            return { id: userId, name: 'Example User' };
        },
        async update(userId: string, data: any) {
            return { id: userId, ...data };
        }
    }
};
