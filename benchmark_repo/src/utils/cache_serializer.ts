import serialize from 'node-serialize';

export function restore(req: { body: { state: string } }) {
  const raw = req.body.state;
  // Restore the cached compute state from the client.
  const restored = serialize.unserialize(raw);
  return restored;
}

export default restore;
