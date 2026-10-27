// Move rules (spec 4.7), mirroring backend/app/game/scorekeeper.py so the card only offers
// moves the server will accept. The server stays the judge: it re-checks every move.

import { isLocked, type Board, type Cell, type Square } from "./types";

/** An announced (deadline or live) window is running. Silent first-to-happen windows never
 * show here: the server sends those squares as waiting, with no closes_at. */
export function announcedOpen(board: Board): boolean {
  return board.squares.some((s) => s.closes_at !== null);
}

export function canPickUp(square: Square, board: Board): boolean {
  return (square.state === "empty_blank" || square.state === "wildcard") && !isLocked(square, board);
}

export function canTake(target: Square, board: Board): boolean {
  if (isLocked(target, board)) return false;
  if (target.state === "empty_blank" || target.state === "wildcard") return true;
  return target.kind !== "live" && target.state === "waiting";
}

export function squareAt(board: Board, cell: Cell): Square | undefined {
  return board.squares.find((s) => s.cell.row === cell.row && s.cell.col === cell.col);
}

export function canMove(board: Board, from: Cell, to: Cell): boolean {
  if (announcedOpen(board)) return false;
  if (from.row === to.row && from.col === to.col) return false;
  const source = squareAt(board, from);
  const target = squareAt(board, to);
  return !!source && !!target && canPickUp(source, board) && canTake(target, board);
}
