export type Prop = {
  id: string; eventId: string; event: string; startsAt: string; player: string;
  market: string; line: number; side: 'Over' | 'Under'; book: 'DraftKings' | 'FanDuel'; odds: number; updatedAt: string;
};
export type PropsPayload = { props: Prop[]; eventsChecked: number; remainingCredits?: string; fetchedAt: string; warnings: string[] };
