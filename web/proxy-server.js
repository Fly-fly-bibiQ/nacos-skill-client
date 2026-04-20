const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const path = require('path');

const app = express();

// Serve static files
app.use(express.static(path.join(__dirname, 'dist')));

// Proxy /api to backend
app.use('/api', createProxyMiddleware({
  target: 'http://127.0.0.1:8899',
  changeOrigin: true,
  ws: true,
}));

app.listen(5173, () => {
  console.log('Serving on http://localhost:5173');
});
