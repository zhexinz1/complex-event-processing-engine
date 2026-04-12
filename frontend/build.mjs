import { spawn } from 'node:child_process';

const args = process.argv.slice(2);
const showBacktest = args.includes('--show-backtest');
const viteArgs = args.filter((arg) => arg !== '--show-backtest');
const viteBin = process.platform === 'win32' ? 'vite.cmd' : 'vite';

const child = spawn(
  viteBin,
  ['build', '--config', 'frontend/vite.config.ts', ...viteArgs],
  {
    env: {
      ...process.env,
      VITE_SHOW_BACKTEST: showBacktest ? 'true' : 'false',
    },
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
