/**
 * ECharts 主题（深空黑底 / 浅色白底，与站点主题同步）
 * 仅影响图表配色与文字颜色，不改动任何数据与交互逻辑。
 * 用法：echarts.init(dom, chartThemeName())
 */
import * as echarts from 'echarts'
import { isDark } from './theme-mode'

export const DEEP_ECHARTS_THEME = 'healthybot-deep'
export const LIGHT_ECHARTS_THEME = 'healthybot-light'

/** 当前应使用的图表主题名（跟随站点黑白切换） */
export function chartThemeName() {
  return isDark.value ? DEEP_ECHARTS_THEME : LIGHT_ECHARTS_THEME
}

echarts.registerTheme(DEEP_ECHARTS_THEME, {
  color: ['#4de3ff', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#60a5fa'],
  backgroundColor: 'transparent',
  textStyle: { color: '#c6cfee' },
  title: { textStyle: { color: '#e6ecff' }, subtextStyle: { color: '#8b96c9' } },
  legend: { textStyle: { color: '#c6cfee' } },
  tooltip: {
    backgroundColor: 'rgba(15, 21, 48, .96)',
    borderColor: 'rgba(77, 227, 255, .3)',
    textStyle: { color: '#e6ecff' },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: 'rgba(139, 150, 201, .3)' } },
    axisTick: { lineStyle: { color: 'rgba(139, 150, 201, .3)' } },
    axisLabel: { color: '#8b96c9' },
    splitLine: { lineStyle: { color: 'rgba(139, 150, 201, .12)' } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: 'rgba(139, 150, 201, .3)' } },
    axisTick: { lineStyle: { color: 'rgba(139, 150, 201, .3)' } },
    axisLabel: { color: '#8b96c9' },
    splitLine: { lineStyle: { color: 'rgba(139, 150, 201, .12)' } },
  },
  radar: {
    axisName: { color: '#8b96c9' },
    axisLine: { lineStyle: { color: 'rgba(139, 150, 201, .28)' } },
    splitLine: { lineStyle: { color: 'rgba(139, 150, 201, .22)' } },
    splitArea: { areaStyle: { color: ['rgba(77, 227, 255, .04)', 'rgba(167, 139, 250, .06)'] } },
  },
  pie: { itemStyle: { borderColor: '#0f1530', borderWidth: 2 } },
  line: { symbolSize: 6, itemStyle: { borderWidth: 2 } },
  bar: { itemStyle: { barBorderRadius: [6, 6, 0, 0] } },
  graph: { itemStyle: { borderColor: '#0f1530' } },
})

echarts.registerTheme(LIGHT_ECHARTS_THEME, {
  color: ['#2b7de9', '#7c5cf0', '#22a06b', '#e2a03f', '#e0517d', '#0e7490'],
  backgroundColor: 'transparent',
  textStyle: { color: '#263238' },
  title: { textStyle: { color: '#17243d' }, subtextStyle: { color: '#71809a' } },
  legend: { textStyle: { color: '#526582' } },
  tooltip: {
    backgroundColor: 'rgba(255, 255, 255, .98)',
    borderColor: '#dbe3ee',
    textStyle: { color: '#263238' },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#dbe3ee' } },
    axisTick: { lineStyle: { color: '#dbe3ee' } },
    axisLabel: { color: '#71809a' },
    splitLine: { lineStyle: { color: '#eef2f8' } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#dbe3ee' } },
    axisTick: { lineStyle: { color: '#dbe3ee' } },
    axisLabel: { color: '#71809a' },
    splitLine: { lineStyle: { color: '#eef2f8' } },
  },
  radar: {
    axisName: { color: '#71809a' },
    axisLine: { lineStyle: { color: '#dbe3ee' } },
    splitLine: { lineStyle: { color: '#e6ecf5' } },
    splitArea: { areaStyle: { color: ['rgba(43, 125, 233, .04)', 'rgba(124, 92, 240, .06)'] } },
  },
  pie: { itemStyle: { borderColor: '#ffffff', borderWidth: 2 } },
  line: { symbolSize: 6, itemStyle: { borderWidth: 2 } },
  bar: { itemStyle: { barBorderRadius: [6, 6, 0, 0] } },
  graph: { itemStyle: { borderColor: '#ffffff' } },
})
