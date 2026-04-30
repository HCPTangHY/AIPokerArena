const ROLES = [
  { name: '狼人', team: 'werewolf', desc: '每晚刀杀一名玩家' },
  { name: '预言家', team: 'villager', desc: '每晚查验一名玩家身份' },
  { name: '女巫', team: 'villager', desc: '解药+毒药各一瓶' },
  { name: '猎人', team: 'villager', desc: '死亡时可开枪击杀一人' },
  { name: '白痴', team: 'villager', desc: '被放逐可翻牌免死' },
  { name: '守卫', team: 'villager', desc: '每晚守护一名玩家' },
  { name: '村民', team: 'villager', desc: '无特殊能力' },
];

export function RoleLegend() {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.03)',
      borderRadius: '12px',
      border: '1px solid rgba(255,255,255,0.08)',
      padding: '12px',
    }}>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#ccc', marginBottom: '8px' }}>
        📋 角色图鉴
      </div>
      <div style={{ display: 'grid', gap: '4px' }}>
        {ROLES.map(r => (
          <div key={r.name} style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            fontSize: '0.75rem', color: '#aaa',
          }}>
            <span style={{
              width: '8px', height: '8px', borderRadius: '50%',
              background: r.team === 'werewolf' ? '#ef5350' : '#66bb6a',
              flexShrink: 0,
            }} />
            <span style={{ fontWeight: 500, minWidth: '50px' }}>{r.name}</span>
            <span style={{ color: '#777' }}>{r.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
