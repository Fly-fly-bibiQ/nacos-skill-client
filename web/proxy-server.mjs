import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import http from 'http';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();

app.use(express.static(path.join(__dirname, 'dist')));

// Manual proxy for /api to preserve full path
app.use('/api', (req, res) => {
  const options = {
    hostname: '127.0.0.1',
    port: 8899,
    path: req.originalUrl,  // Full path including /api
    method: req.method,
    headers: req.headers,
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on('error', (e) => {
    res.status(500).json({ error: 'Proxy error: ' + e.message });
  });

  req.pipe(proxyReq);
});

app.listen(5173, () => {
  console.log('Serving on http://localhost:5173');
});
