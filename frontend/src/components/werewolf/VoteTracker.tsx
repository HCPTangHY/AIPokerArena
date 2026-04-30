import type { WerewolfGameState, WerewolfPlayer } from '../../types/werewolf';

interface Props {
  gameState: WerewolfGameState | null;
  players: WerewolfPlayer[];
  showEmpty?: boolean;
}

const ABSTAIN_KEY = '__abstain__';

function formatVoteCount(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
}

export function VoteTracker({ gameState, players, showEmpty }: Props) {
  if (!gameState) {
    if (!showEmpty) return null;
    return (
      <section className="werewolf-vote-tracker is-empty">
        <div className="werewolf-vote-title">
          <strong>投票情况</strong>
          <span>等待对局数据</span>
        </div>
        <p className="werewolf-vote-empty">开局后这里会显示实时票型。</p>
      </section>
    );
  }

  const { votes, vote_result, sheriff_vote_result } = gameState;
  const voteEntries = Object.entries(votes);
  const showSheriffResult = gameState.phase !== 'vote' && voteEntries.length === 0 && !vote_result && Boolean(sheriff_vote_result);

  if (voteEntries.length === 0 && !vote_result && !sheriff_vote_result) {
    if (!showEmpty) return null;
    return (
      <section className="werewolf-vote-tracker is-empty">
        <div className="werewolf-vote-title">
          <strong>投票情况</strong>
          <span>暂无投票</span>
        </div>
        <p className="werewolf-vote-empty">进入放逐投票后，票数和投票流向会在这里更新。</p>
      </section>
    );
  }

  const getName = (pid: string) => players.find(p => p.id === pid)?.display_name || pid;
  const getVoteWeight = (voterId: string) => voterId === gameState.sheriff_id ? 1.5 : 1;
  const displayVoteEntries = showSheriffResult
    ? Object.entries(sheriff_vote_result?.votes || {})
    : voteEntries;
  const liveTally = displayVoteEntries.reduce<Record<string, number>>((acc, [voterId, targetId]) => {
    const key = targetId || ABSTAIN_KEY;
    acc[key] = (acc[key] || 0) + (targetId ? (showSheriffResult ? 1 : getVoteWeight(voterId)) : 1);
    return acc;
  }, {});
  const sheriffTally = sheriff_vote_result
    ? sheriff_vote_result.candidate_ids.reduce<Record<string, number>>((acc, candidateId) => {
        acc[candidateId] = sheriff_vote_result.tally[candidateId] || 0;
        return acc;
      }, {
        ...Object.entries(sheriff_vote_result.votes).reduce<Record<string, number>>((acc, [, targetId]) => {
          if (!targetId) acc[ABSTAIN_KEY] = (acc[ABSTAIN_KEY] || 0) + 1;
          return acc;
        }, {}),
      })
    : null;
  const resultTally = vote_result
    ? {
        ...vote_result.tally,
        ...Object.entries(vote_result.votes).reduce<Record<string, number>>((acc, [, targetId]) => {
          if (!targetId) acc[ABSTAIN_KEY] = (acc[ABSTAIN_KEY] || 0) + 1;
          return acc;
        }, {}),
      }
    : null;
  const sortedTally = Object.entries((showSheriffResult ? sheriffTally : resultTally) || liveTally)
    .sort(([, countA], [, countB]) => countB - countA);

  return (
    <section className="werewolf-vote-tracker">
      <div className="werewolf-vote-title">
        <strong>{showSheriffResult ? '警长票型' : '投票情况'}</strong>
        <span>
          {showSheriffResult
            ? '竞选结果'
            : vote_result
              ? '投票结果'
              : `${voteEntries.length} 人已投`}
        </span>
      </div>

      {sortedTally.length > 0 && (
        <div className="werewolf-vote-tally">
          {sortedTally.map(([pid, count]) => (
            <div
              key={pid}
              className={`werewolf-vote-row ${pid === vote_result?.eliminated_id || (showSheriffResult && pid === sheriff_vote_result?.winner_id) ? 'is-eliminated' : ''}`}
            >
              <span>{pid === ABSTAIN_KEY ? (showSheriffResult ? '弃权/无效' : '弃权') : getName(pid)}</span>
              <strong>{formatVoteCount(count)} {pid === ABSTAIN_KEY ? '人' : '票'}</strong>
            </div>
          ))}
        </div>
      )}

      {vote_result?.eliminated_id && (
        <div className="werewolf-vote-result">
          {vote_result.eliminated_name} 被放逐出局
        </div>
      )}

      {!showSheriffResult && vote_result?.is_tie && !vote_result.no_elimination && (
        <div className="werewolf-vote-result">
          平票，进入PK发言
        </div>
      )}

      {!showSheriffResult && vote_result?.no_elimination && (
        <div className="werewolf-vote-result">
          本轮无人被放逐
        </div>
      )}

      {showSheriffResult && sheriff_vote_result?.winner_id && (
        <div className="werewolf-vote-result">
          {sheriff_vote_result.winner_name} 当选警长
        </div>
      )}

      {showSheriffResult && sheriff_vote_result?.is_tie && !sheriff_vote_result.no_sheriff && (
        <div className="werewolf-vote-result">
          平票，进入警长PK
        </div>
      )}

      {showSheriffResult && sheriff_vote_result?.no_sheriff && (
        <div className="werewolf-vote-result">
          本局无警徽
        </div>
      )}

      {(showSheriffResult || (!vote_result && voteEntries.length > 0)) && (
        <div className="werewolf-vote-flows">
          {displayVoteEntries.map(([voterId, targetId]) => (
            <div key={voterId}>
              {getName(voterId)} → {targetId ? getName(targetId) : showSheriffResult ? '弃权/无效' : '弃权'}
              {!showSheriffResult && voterId === gameState.sheriff_id && targetId ? '（1.5票）' : ''}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
