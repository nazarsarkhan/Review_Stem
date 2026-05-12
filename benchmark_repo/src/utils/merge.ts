import _ from 'lodash';

export function applyUserSettings(defaults: any, body: any) {
  const merged = _.merge({}, defaults, body);
  return merged;
}

export default applyUserSettings;
