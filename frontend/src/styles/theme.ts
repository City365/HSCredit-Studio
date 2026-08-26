import { theme as antdTheme } from 'antd';

export const theme = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
    fontSize: 14,
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      siderBg: '#fafafa',
    },
    Menu: {
      itemBg: 'transparent',
    },
  },
};

export const darkTheme = {
  ...theme,
  algorithm: antdTheme.darkAlgorithm,
};
