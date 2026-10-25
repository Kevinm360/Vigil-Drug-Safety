// Keep leaf routes stable for bookmarks, investigation saves, and reaction links.
export const NAV_GROUPS = [
  {id:'overview',label:'Overview',views:['overview']},
  {id:'explore',label:'Explore',views:['reactions','signals','changes','network']},
  {id:'reports',label:'Reports',views:['reports','severity']},
  {id:'lab',label:'Lab',views:['narratives','models']},
];

export const VIEW_NAV_LABELS = {
  overview:'Overview',reactions:'Reactions',signals:'Signals',changes:'What changed?',
  network:'Network',reports:'Case reports',severity:'Severity & demographics',
  narratives:'Narrative analysis',models:'Model studio',
};

export function groupForView(view){
  return NAV_GROUPS.find(group=>group.views.includes(view))||NAV_GROUPS[0];
}

export function groupDestination(groupId,lastViews={}){
  const group=NAV_GROUPS.find(item=>item.id===groupId)||NAV_GROUPS[0];
  return group.views.includes(lastViews[group.id])?lastViews[group.id]:group.views[0];
}
