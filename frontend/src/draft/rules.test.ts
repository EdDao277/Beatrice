import { describe, expect, it } from 'vitest';
import { nextTurn, appendAction, unavailable } from './rules';
import type { Action, Format } from './rules';

describe('draft rules', () => {
  it('allows either side to enter ranked bans and opposing duplicate bans', () => {
    let actions: Action[] = [];
    actions = appendAction('RANKED', actions, 'RED', 'Swain');
    expect(unavailable('RANKED', actions, 'BLUE')).not.toContain('Swain');
    actions = appendAction('RANKED', actions, 'BLUE', 'Swain');
    expect(() => appendAction('RANKED', actions, 'BLUE', 'Swain')).toThrow();
    for (let i = 0; i < 4; i++) actions = appendAction('RANKED', actions, 'RED', null);
    expect(() => appendAction('RANKED', actions, 'RED', null)).toThrow();
    for (let i = 0; i < 4; i++) actions = appendAction('RANKED', actions, 'BLUE', null);
    expect(nextTurn('RANKED', actions)).toEqual({ kind: 'PICK', side: 'BLUE' });
    expect(unavailable('RANKED', actions, 'BLUE')).toContain('Swain');
  });
  it.each<[Format, string]>([
    ['RANKED', 'BLUE,RED,RED,BLUE,BLUE,RED,RED,BLUE,BLUE,RED'],
    ['TOURNAMENT', 'BLUE,RED,BLUE,RED,BLUE,RED,BLUE,RED,RED,BLUE,BLUE,RED,RED,BLUE,RED,BLUE,RED,BLUE,BLUE,RED'],
  ])('enforces the complete %s sequence', (format, order) => {
    let actions: Action[] = [];
    if (format === 'RANKED') for (const side of ['BLUE', 'RED'] as const)
      for (let n = 0; n < 5; n++) actions = appendAction(format, actions, side, null);
    order.split(',').forEach((side, n) => {
      expect(nextTurn(format, actions)?.side).toBe(side);
      actions = appendAction(format, actions, side as 'BLUE' | 'RED', 'Champion' + n);
    });
    expect(nextTurn(format, actions)).toBeNull();
    expect(() => appendAction(format, actions, 'BLUE', 'Extra')).toThrow();
    expect(nextTurn(format, actions.slice(0, -1))).toEqual({ kind: 'PICK', side: 'RED' });
  });
  it('rejects wrong side, duplicate tournament selections, and empty picks', () => {
    const first = appendAction('TOURNAMENT', [], 'BLUE', 'Swain');
    expect(() => appendAction('TOURNAMENT', first, 'BLUE', 'Ahri')).toThrow();
    expect(() => appendAction('TOURNAMENT', first, 'RED', 'Swain')).toThrow();
    let actions: Action[] = [];
    for (let n = 0; n < 6; n++) actions = appendAction('TOURNAMENT', actions, n % 2 ? 'RED' : 'BLUE', null);
    expect(() => appendAction('TOURNAMENT', actions, 'BLUE', null)).toThrow();
  });
});
