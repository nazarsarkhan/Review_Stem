import express from 'express';
import { db } from '../db';

const router = express.Router();

// PERFORMANCE ISSUE: N+1 query problem
router.get('/posts', async (req, res) => {
  // First query: fetch all posts
  const posts = await db.posts.findAll();

  // N queries: fetch author for each post individually
  // If there are 100 posts, this makes 101 total queries (1 + 100)
  for (const post of posts) {
    post.author = await db.users.findById(post.authorId);
  }

  res.json(posts);
});

// PERFORMANCE ISSUE: N+1 with comments
router.get('/posts/:id', async (req, res) => {
  const postId = parseInt(req.params.id);
  const post = await db.posts.findById(postId);

  if (!post) {
    return res.status(404).json({ error: 'Post not found' });
  }

  // Fetch comments
  const comments = await db.comments.findByPostId(postId);

  // N+1: fetch author for each comment
  for (const comment of comments) {
    comment.author = await db.users.findById(comment.authorId);
  }

  post.comments = comments;
  res.json(post);
});

export default router;
