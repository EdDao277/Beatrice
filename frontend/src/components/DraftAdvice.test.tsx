import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import useDraftAdvice from './useDraftAdvice';
import type { Action } from '../draft/rules';
afterEach(cleanup);
function Harness({ actions = [] }: { actions?: Action[] }) {
  const advice = useDraftAdvice({ format: 'RANKED', actions });
  return <>{advice.left}{advice.right}</>;
}
it('shows phase-aware advice without draft configuration or invented scores', () => {
  const { rerender } = render(<Harness />);
  expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  expect(screen.getByText('Ban phase')).toBeInTheDocument();
  expect(screen.getByText(/engine update is next/i)).toBeInTheDocument();
  const bans: Action[] = Array.from({ length: 10 }, (_, i) => ({ kind: 'BAN', side: i < 5 ? 'BLUE' : 'RED', championId: null }));
  rerender(<Harness actions={bans} />);
  expect(screen.getByText('Blind pick')).toBeInTheDocument();
  rerender(<Harness actions={[...bans, { kind: 'PICK', side: 'BLUE', championId: 'Swain' }]} />);
  expect(screen.getByText('Pick phase')).toBeInTheDocument();
});
