const store = new Map<string, string>();

export const cache = {
    async get(key: string) {
        return store.get(key);
    },
    async set(key: string, value: string) {
        store.set(key, value);
    },
    async del(key: string) {
        store.delete(key);
    }
};
