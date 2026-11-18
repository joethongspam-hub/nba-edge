import { NextResponse } from 'next/server';
import type { Prop, PropsPayload } from '../../../lib/types';

export const dynamic = 'force-dynamic';
const ROOT = 'https://api.the-odds-api.com/v4/sports/basketball_nba';
const MARKETS = ['player_points', 'player_rebounds', 'player_assists', 'player_threes'];
const BOOKS: Record<string, Prop['book']> = { draftkings: 'DraftKings', fanduel: 'FanDuel' };
type Event = { id: string; home_team: string; away_team: string; commence_time: string };
type Outcome = { name: string; description?: string; point?: number; price?: number };
type EventOdds = { id: string; home_team: string; away_team: string; commence_time: string; bookmakers?: Array<{key:string; last_update?:string; markets?:Array<{key:string; outcomes?:Outcome[]}>}> };
const safeError = (s: number) => s === 401 || s === 403 ? 'Odds API rejected your key or access level.' : s === 429 ? 'Odds API rate limit reached.' : `Odds provider returned HTTP ${s}.`;

export async function GET() {
  const key = process.env.ODDS_API_KEY;
  if (!key) return NextResponse.json({error:'ODDS_API_KEY is not configured. Add it in Vercel Environment Variables.'}, {status:503});
  try {
    const headers = {'x-api-key': key};
    const eventsResponse = await fetch(`${ROOT}/events`, {headers, next:{revalidate:300}});
    if (!eventsResponse.ok) return NextResponse.json({error:safeError(eventsResponse.status)}, {status:502});
    const allEvents = await eventsResponse.json() as Event[];
    const events = allEvents.filter(e=>new Date(e.commence_time).getTime() > Date.now()).slice(0, 8);
    const warnings:string[] = [];
    const props: Prop[] = [];
    let remainingCredits = eventsResponse.headers.get('x-requests-remaining') ?? undefined;
    // Keep costs bounded: up to 8 game-specific prop calls per refresh, cached for 5 minutes.
    // Your Odds API plan determines available markets and usage credits.
    const responses = await Promise.all(events.map(async (event) => {
      const params = new URLSearchParams({regions:'us',bookmakers:'draftkings,fanduel',markets:MARKETS.join(','),oddsFormat:'american'});
      const result = await fetch(`${ROOT}/events/${encodeURIComponent(event.id)}/odds?${params}`, {headers, next:{revalidate:300}});
      return {event, result};
    }));
    for (const {event, result} of responses) {
      remainingCredits = result.headers.get('x-requests-remaining') ?? remainingCredits;
      if (!result.ok) {warnings.push(`${event.away_team} @ ${event.home_team}: ${safeError(result.status)}`); continue;}
      const details = await result.json() as EventOdds;
      for (const book of details.bookmakers ?? []) {
        const bookName = BOOKS[book.key]; if (!bookName) continue;
        for (const market of book.markets ?? []) {
          for (const outcome of market.outcomes ?? []) {
            if ((outcome.name !== 'Over' && outcome.name !== 'Under') || !outcome.description || typeof outcome.point !== 'number' || typeof outcome.price !== 'number') continue;
            const side = outcome.name as 'Over'|'Under';
            props.push({id:`${details.id}:${book.key}:${market.key}:${outcome.description}:${outcome.point}:${side}`,eventId:details.id,event:`${details.away_team} @ ${details.home_team}`,startsAt:details.commence_time,player:outcome.description,market:market.key,line:outcome.point,side,book:bookName,odds:outcome.price,updatedAt:book.last_update ?? ''});
          }
        }
      }
    }
    const payload: PropsPayload = {props,eventsChecked:events.length,remainingCredits,fetchedAt:new Date().toISOString(),warnings};
    return NextResponse.json(payload, {headers:{'Cache-Control':'public, s-maxage=300, stale-while-revalidate=60'}});
  } catch {return NextResponse.json({error:'Unable to contact the odds provider. Please retry later.'}, {status:502});}
}
