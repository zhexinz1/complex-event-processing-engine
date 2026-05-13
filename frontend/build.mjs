import { spawn } from 'node:child_process';

const args = process.argv.slice(2);
const viteBin = process.platform === 'win32' ? 'vite.cmd' : 'vite';

const child = spawn(
  viteBin,
  ['build', '--config', 'frontend/vite.config.ts', ...args],
  {
    env: process.env,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  },
);

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
