let transferredSession = null;

export function setTransferredStorySession(session) {
  transferredSession = session || null;
}

export function consumeTransferredStorySession() {
  const nextSession = transferredSession;
  transferredSession = null;
  return nextSession;
}
