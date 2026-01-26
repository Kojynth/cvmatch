"""
Générateur de rapports d'overfitting pour l'extraction CV.
Fournit des analyses détaillées et des visualisations des métriques.
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

from .overfitting_monitor import overfitting_monitor


class OverfittingReporter:
    """Générateur de rapports d'overfitting avancés."""
    
    def __init__(self, output_dir: str = "reports/overfitting"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Style des graphiques
        plt.style.use('seaborn-v0_8' if 'seaborn-v0_8' in plt.style.available else 'default')
        sns.set_palette("husl")
    
    def generate_comprehensive_report(self, title: str = "Rapport d'Overfitting CV Extractor") -> str:
        """Génère un rapport complet d'overfitting."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_dir = self.output_dir / f"report_{timestamp}"
        report_dir.mkdir(exist_ok=True)
        
        logger.info(f"📊 Génération du rapport d'overfitting : {report_dir}")
        
        # Récupérer les données du moniteur
        health_report = overfitting_monitor.get_health_report()
        metrics_data = overfitting_monitor.metrics_history
        alerts_data = overfitting_monitor.alerts_history
        
        if not metrics_data:
            logger.warning("Aucune donnée de métriques disponible pour le rapport")
            return self._generate_empty_report(report_dir, title)
        
        # Convertir en DataFrame pour analyse
        df_metrics = pd.DataFrame([
            {
                'cv_id': m.cv_id,
                'timestamp': m.extraction_timestamp,
                'avg_confidence': m.avg_confidence,
                'low_confidence_ratio': m.low_confidence_ratio,
                'empty_fields_ratio': m.empty_fields_ratio,
                'extraction_complexity': m.extraction_complexity,
                'pattern_diversity': m.pattern_diversity,
                'geometric_coherence': m.geometric_coherence,
                'extraction_time_ms': m.extraction_time_ms,
                'experiences_extracted': m.experiences_extracted,
                'education_extracted': m.education_extracted,
                'skills_extracted': m.skills_extracted,
                'total_extracted': m.experiences_extracted + m.education_extracted + m.skills_extracted
            }
            for m in metrics_data
        ])
        
        # Générer les sections du rapport
        sections = {
            "01_summary": self._generate_executive_summary(health_report, df_metrics, alerts_data),
            "02_trends": self._generate_trends_analysis(df_metrics, report_dir),
            "03_alerts": self._generate_alerts_analysis(alerts_data, report_dir),
            "04_performance": self._generate_performance_analysis(df_metrics, report_dir),
            "05_recommendations": self._generate_recommendations(health_report, df_metrics, alerts_data)
        }
        
        # Générer le rapport HTML principal
        html_report = self._generate_html_report(title, sections, health_report)
        report_file = report_dir / "overfitting_report.html"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_report)
        
        # Exporter les données brutes
        self._export_raw_data(df_metrics, alerts_data, report_dir)
        
        logger.info(f"✅ Rapport généré : {report_file}")
        return str(report_file)
    
    def _generate_executive_summary(self, health_report: Dict, df_metrics: pd.DataFrame, alerts_data: List) -> str:
        """Génère le résumé exécutif."""
        status = health_report.get('status', 'unknown')
        recent_extractions = len(df_metrics.tail(10))
        
        # Statistiques clés
        avg_confidence = df_metrics['avg_confidence'].mean()
        avg_time = df_metrics['extraction_time_ms'].mean()
        avg_success_rate = 1 - df_metrics['empty_fields_ratio'].mean()
        
        # Tendances
        if len(df_metrics) >= 10:
            recent_confidence = df_metrics.tail(10)['avg_confidence'].mean()
            older_confidence = df_metrics.head(10)['avg_confidence'].mean()
            confidence_trend = "📈 En hausse" if recent_confidence > older_confidence else "📉 En baisse"
        else:
            confidence_trend = "➡️ Stable"
        
        # Compter les alertes par niveau
        alert_counts = {}
        for alert in alerts_data:
            level = getattr(alert, 'alert_level', 'unknown')
            alert_counts[level] = alert_counts.get(level, 0) + 1
        
        status_emoji = {
            'healthy': '✅',
            'caution': '⚠️',
            'warning': '🔶',
            'critical': '🚨'
        }.get(status, '❓')
        
        return f"""
        <div class="summary-section">
            <h2>📋 Résumé Exécutif</h2>
            
            <div class="status-card status-{status}">
                <h3>{status_emoji} Statut Global : {status.title()}</h3>
                <p>Basé sur l'analyse de {len(df_metrics)} extractions</p>
            </div>
            
            <div class="metrics-grid">
                <div class="metric-card">
                    <h4>📊 Confiance Moyenne</h4>
                    <div class="metric-value">{avg_confidence:.2f}</div>
                    <div class="metric-trend">{confidence_trend}</div>
                </div>
                
                <div class="metric-card">
                    <h4>⏱️ Temps Moyen</h4>
                    <div class="metric-value">{avg_time:.0f}ms</div>
                </div>
                
                <div class="metric-card">
                    <h4>✅ Taux de Réussite</h4>
                    <div class="metric-value">{avg_success_rate:.1%}</div>
                </div>
                
                <div class="metric-card">
                    <h4>🚨 Alertes Récentes</h4>
                    <div class="metric-value">{len(alerts_data)}</div>
                    <div class="alert-breakdown">
                        {self._format_alert_breakdown(alert_counts)}
                    </div>
                </div>
            </div>
        </div>
        """
    
    def _format_alert_breakdown(self, alert_counts: Dict[str, int]) -> str:
        """Formate la répartition des alertes."""
        if not alert_counts:
            return "Aucune alerte"
        
        breakdown = []
        level_emojis = {'low': '⚠️', 'medium': '🔶', 'high': '🔴', 'critical': '🚨'}
        
        for level, count in alert_counts.items():
            emoji = level_emojis.get(level, '❓')
            breakdown.append(f"{emoji} {count}")
        
        return " | ".join(breakdown)
    
    def _generate_trends_analysis(self, df_metrics: pd.DataFrame, report_dir: Path) -> str:
        """Génère l'analyse des tendances avec graphiques."""
        
        # Graphique 1 : Évolution de la confiance
        plt.figure(figsize=(12, 6))
        plt.subplot(2, 2, 1)
        plt.plot(df_metrics.index, df_metrics['avg_confidence'], marker='o')
        plt.title('Évolution de la Confiance Moyenne')
        plt.ylabel('Confiance')
        plt.xlabel('Extraction #')
        plt.grid(True, alpha=0.3)
        
        # Graphique 2 : Temps d'extraction
        plt.subplot(2, 2, 2)
        plt.plot(df_metrics.index, df_metrics['extraction_time_ms'], marker='s', color='orange')
        plt.title('Temps d\'Extraction')
        plt.ylabel('Temps (ms)')
        plt.xlabel('Extraction #')
        plt.grid(True, alpha=0.3)
        
        # Graphique 3 : Diversité des patterns
        plt.subplot(2, 2, 3)
        plt.plot(df_metrics.index, df_metrics['pattern_diversity'], marker='^', color='green')
        plt.title('Diversité des Patterns')
        plt.ylabel('Diversité')
        plt.xlabel('Extraction #')
        plt.grid(True, alpha=0.3)
        
        # Graphique 4 : Distribution de confiance
        plt.subplot(2, 2, 4)
        plt.hist(df_metrics['avg_confidence'], bins=20, alpha=0.7, color='purple')
        plt.title('Distribution de la Confiance')
        plt.xlabel('Confiance')
        plt.ylabel('Fréquence')
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        chart_path = report_dir / "trends_analysis.png"
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Calcul des statistiques de tendance
        recent_window = min(10, len(df_metrics))
        if recent_window > 1:
            recent_data = df_metrics.tail(recent_window)
            confidence_trend = recent_data['avg_confidence'].corr(pd.Series(range(len(recent_data))))
            time_trend = recent_data['extraction_time_ms'].corr(pd.Series(range(len(recent_data))))
        else:
            confidence_trend = 0
            time_trend = 0
        
        return f"""
        <div class="trends-section">
            <h2>📈 Analyse des Tendances</h2>
            
            <div class="chart-container">
                <img src="trends_analysis.png" alt="Graphiques de tendances" class="chart-image">
            </div>
            
            <div class="trend-stats">
                <h3>📊 Statistiques de Tendance</h3>
                <ul>
                    <li><strong>Corrélation confiance :</strong> {confidence_trend:.3f} 
                        {"📈 Amélioration" if confidence_trend > 0.1 else "📉 Dégradation" if confidence_trend < -0.1 else "➡️ Stable"}</li>
                    <li><strong>Corrélation temps :</strong> {time_trend:.3f}
                        {"⏳ Ralentissement" if time_trend > 0.1 else "⚡ Accélération" if time_trend < -0.1 else "➡️ Stable"}</li>
                    <li><strong>Variance confiance :</strong> {df_metrics['avg_confidence'].var():.4f}</li>
                    <li><strong>Variance temps :</strong> {df_metrics['extraction_time_ms'].var():.0f}</li>
                </ul>
            </div>
        </div>
        """
    
    def _generate_alerts_analysis(self, alerts_data: List, report_dir: Path) -> str:
        """Génère l'analyse des alertes."""
        if not alerts_data:
            return """
            <div class="alerts-section">
                <h2>🚨 Analyse des Alertes</h2>
                <div class="no-alerts">
                    ✅ Aucune alerte d'overfitting détectée récemment
                </div>
            </div>
            """
        
        # Compter les alertes par type et niveau
        alert_summary = {}
        level_counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        
        for alert in alerts_data:
            level = getattr(alert, 'alert_level', 'unknown')
            metric = getattr(alert, 'metric_name', 'unknown')
            message = getattr(alert, 'message', 'No message')
            
            level_counts[level] = level_counts.get(level, 0) + 1
            
            if metric not in alert_summary:
                alert_summary[metric] = []
            alert_summary[metric].append({
                'level': level,
                'message': message,
                'value': getattr(alert, 'current_value', 'N/A'),
                'threshold': getattr(alert, 'threshold_value', 'N/A')
            })
        
        # Générer la table des alertes
        alerts_table = "<table class='alerts-table'>"
        alerts_table += "<tr><th>Métrique</th><th>Niveau</th><th>Message</th><th>Valeur</th><th>Seuil</th></tr>"
        
        for metric, alerts in alert_summary.items():
            for alert in alerts:
                level_emoji = {'low': '⚠️', 'medium': '🔶', 'high': '🔴', 'critical': '🚨'}.get(alert['level'], '❓')
                alerts_table += f"""
                <tr class="alert-{alert['level']}">
                    <td>{metric}</td>
                    <td>{level_emoji} {alert['level']}</td>
                    <td>{alert['message']}</td>
                    <td>{alert['value']}</td>
                    <td>{alert['threshold']}</td>
                </tr>
                """
        
        alerts_table += "</table>"
        
        return f"""
        <div class="alerts-section">
            <h2>🚨 Analyse des Alertes</h2>
            
            <div class="alert-summary">
                <h3>📊 Résumé des Alertes</h3>
                <div class="alert-counts">
                    <span class="alert-count critical">🚨 Critical: {level_counts.get('critical', 0)}</span>
                    <span class="alert-count high">🔴 High: {level_counts.get('high', 0)}</span>
                    <span class="alert-count medium">🔶 Medium: {level_counts.get('medium', 0)}</span>
                    <span class="alert-count low">⚠️ Low: {level_counts.get('low', 0)}</span>
                </div>
            </div>
            
            <div class="alerts-details">
                <h3>📋 Détail des Alertes</h3>
                {alerts_table}
            </div>
        </div>
        """
    
    def _generate_performance_analysis(self, df_metrics: pd.DataFrame, report_dir: Path) -> str:
        """Génère l'analyse de performance."""
        
        # Graphique de corrélation performance
        plt.figure(figsize=(10, 6))
        
        plt.subplot(1, 2, 1)
        plt.scatter(df_metrics['extraction_time_ms'], df_metrics['avg_confidence'], alpha=0.6)
        plt.xlabel('Temps d\'extraction (ms)')
        plt.ylabel('Confiance moyenne')
        plt.title('Corrélation Temps vs Confiance')
        plt.grid(True, alpha=0.3)
        
        plt.subplot(1, 2, 2)
        plt.scatter(df_metrics['total_extracted'], df_metrics['avg_confidence'], alpha=0.6, color='orange')
        plt.xlabel('Éléments extraits')
        plt.ylabel('Confiance moyenne')
        plt.title('Corrélation Volume vs Confiance')
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        perf_chart_path = report_dir / "performance_analysis.png"
        plt.savefig(perf_chart_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        # Calcul des métriques de performance
        time_confidence_corr = df_metrics['extraction_time_ms'].corr(df_metrics['avg_confidence'])
        volume_confidence_corr = df_metrics['total_extracted'].corr(df_metrics['avg_confidence'])
        
        # Identifier les outliers
        time_q95 = df_metrics['extraction_time_ms'].quantile(0.95)
        slow_extractions = len(df_metrics[df_metrics['extraction_time_ms'] > time_q95])
        
        conf_q05 = df_metrics['avg_confidence'].quantile(0.05)
        low_conf_extractions = len(df_metrics[df_metrics['avg_confidence'] < conf_q05])
        
        return f"""
        <div class="performance-section">
            <h2>⚡ Analyse de Performance</h2>
            
            <div class="chart-container">
                <img src="performance_analysis.png" alt="Analyse de performance" class="chart-image">
            </div>
            
            <div class="performance-stats">
                <h3>📊 Métriques de Performance</h3>
                <div class="stats-grid">
                    <div class="stat-item">
                        <strong>Corrélation Temps-Confiance:</strong> {time_confidence_corr:.3f}
                        <div class="stat-interpretation">
                            {"⚠️ Temps élevé = confiance faible" if time_confidence_corr < -0.3 else "✅ Pas de corrélation négative"}
                        </div>
                    </div>
                    
                    <div class="stat-item">
                        <strong>Corrélation Volume-Confiance:</strong> {volume_confidence_corr:.3f}
                        <div class="stat-interpretation">
                            {"✅ Plus d'éléments = plus de confiance" if volume_confidence_corr > 0.3 else "⚠️ Volume ne garantit pas la qualité"}
                        </div>
                    </div>
                    
                    <div class="stat-item">
                        <strong>Extractions lentes (>P95):</strong> {slow_extractions}
                        <div class="stat-interpretation">
                            {"🔴 Beaucoup d'extractions lentes" if slow_extractions > len(df_metrics) * 0.1 else "✅ Performance acceptable"}
                        </div>
                    </div>
                    
                    <div class="stat-item">
                        <strong>Extractions faible confiance:</strong> {low_conf_extractions}
                        <div class="stat-interpretation">
                            {"🔴 Trop d'extractions peu fiables" if low_conf_extractions > len(df_metrics) * 0.1 else "✅ Confiance globalement bonne"}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
    
    def _generate_recommendations(self, health_report: Dict, df_metrics: pd.DataFrame, alerts_data: List) -> str:
        """Génère les recommandations."""
        recommendations = health_report.get('recommendations', [])
        
        # Ajouter des recommandations spécifiques basées sur l'analyse
        specific_recs = []
        
        if df_metrics['avg_confidence'].var() < 0.01:
            specific_recs.append("📊 Variance de confiance très faible - diversifier les CV de test")
        
        if df_metrics['extraction_time_ms'].mean() > 3000:
            specific_recs.append("⏱️ Temps d'extraction élevé - optimiser les algorithmes")
        
        if df_metrics['empty_fields_ratio'].mean() > 0.3:
            specific_recs.append("📝 Trop de champs vides - améliorer la couverture d'extraction")
        
        if len([a for a in alerts_data if getattr(a, 'alert_level', '') in ['high', 'critical']]) > 0:
            specific_recs.append("🚨 Alertes critiques détectées - intervention immédiate requise")
        
        all_recommendations = recommendations + specific_recs
        
        rec_html = "<ul>"
        for rec in all_recommendations:
            rec_html += f"<li>{rec}</li>"
        rec_html += "</ul>"
        
        return f"""
        <div class="recommendations-section">
            <h2>💡 Recommandations</h2>
            
            <div class="recommendations-list">
                {rec_html}
            </div>
            
            <div class="action-plan">
                <h3>📋 Plan d'Action Prioritaire</h3>
                <ol>
                    <li><strong>Court terme (1-2 jours):</strong> Surveiller les alertes critiques et hautes</li>
                    <li><strong>Moyen terme (1 semaine):</strong> Analyser les patterns d'overfitting détectés</li>
                    <li><strong>Long terme (1 mois):</strong> Améliorer la diversité des données de test</li>
                </ol>
            </div>
        </div>
        """
    
    def _generate_html_report(self, title: str, sections: Dict[str, str], health_report: Dict) -> str:
        """Génère le rapport HTML complet."""
        status = health_report.get('status', 'unknown')
        
        html = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                {self._get_css_styles()}
            </style>
        </head>
        <body>
            <div class="container">
                <header class="report-header">
                    <h1>{title}</h1>
                    <div class="report-meta">
                        <span>Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</span>
                        <span class="status-badge status-{status}">Statut : {status.title()}</span>
                    </div>
                </header>
                
                <nav class="table-of-contents">
                    <h2>📑 Table des Matières</h2>
                    <ul>
                        <li><a href="#summary">Résumé Exécutif</a></li>
                        <li><a href="#trends">Analyse des Tendances</a></li>
                        <li><a href="#alerts">Analyse des Alertes</a></li>
                        <li><a href="#performance">Analyse de Performance</a></li>
                        <li><a href="#recommendations">Recommandations</a></li>
                    </ul>
                </nav>
                
                <main>
                    <section id="summary">{sections['01_summary']}</section>
                    <section id="trends">{sections['02_trends']}</section>
                    <section id="alerts">{sections['03_alerts']}</section>
                    <section id="performance">{sections['04_performance']}</section>
                    <section id="recommendations">{sections['05_recommendations']}</section>
                </main>
                
                <footer class="report-footer">
                    <p>Rapport généré automatiquement par CVMatch Overfitting Monitor</p>
                    <p>Pour plus d'informations, consultez la documentation technique</p>
                </footer>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _get_css_styles(self) -> str:
        """Retourne les styles CSS pour le rapport."""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: white;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        .report-header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 3px solid #007acc;
            margin-bottom: 30px;
        }
        
        .report-header h1 {
            color: #007acc;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .report-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 15px;
        }
        
        .status-badge {
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            text-transform: uppercase;
        }
        
        .status-healthy { background-color: #d4edda; color: #155724; }
        .status-caution { background-color: #fff3cd; color: #856404; }
        .status-warning { background-color: #f8d7da; color: #721c24; }
        .status-critical { background-color: #f5c6cb; color: #721c24; }
        
        .table-of-contents {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        
        .table-of-contents ul {
            list-style: none;
        }
        
        .table-of-contents li {
            margin: 10px 0;
        }
        
        .table-of-contents a {
            color: #007acc;
            text-decoration: none;
            font-weight: 500;
        }
        
        .table-of-contents a:hover {
            text-decoration: underline;
        }
        
        section {
            margin-bottom: 40px;
            padding: 20px;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .metric-card {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            text-align: center;
            border-left: 4px solid #007acc;
        }
        
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #007acc;
            margin: 10px 0;
        }
        
        .metric-trend {
            font-size: 0.9em;
            color: #666;
        }
        
        .chart-container {
            text-align: center;
            margin: 20px 0;
        }
        
        .chart-image {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        
        .alerts-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        .alerts-table th,
        .alerts-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        
        .alerts-table th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        
        .alert-low { background-color: #fff3cd; }
        .alert-medium { background-color: #f8d7da; }
        .alert-high { background-color: #f5c6cb; }
        .alert-critical { background-color: #d1ecf1; }
        
        .alert-counts {
            display: flex;
            gap: 15px;
            margin-top: 15px;
        }
        
        .alert-count {
            padding: 8px 12px;
            border-radius: 15px;
            font-weight: bold;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        
        .stat-item {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
        }
        
        .stat-interpretation {
            font-size: 0.9em;
            color: #666;
            margin-top: 5px;
        }
        
        .recommendations-list ul {
            margin-left: 20px;
        }
        
        .recommendations-list li {
            margin: 10px 0;
        }
        
        .action-plan {
            background-color: #e7f3ff;
            padding: 20px;
            border-radius: 5px;
            margin-top: 20px;
        }
        
        .action-plan ol {
            margin-left: 20px;
        }
        
        .action-plan li {
            margin: 10px 0;
        }
        
        .report-footer {
            text-align: center;
            padding: 30px 0;
            border-top: 1px solid #e0e0e0;
            margin-top: 40px;
            color: #666;
        }
        
        .no-alerts {
            text-align: center;
            padding: 40px;
            background-color: #d4edda;
            color: #155724;
            border-radius: 5px;
            font-size: 1.2em;
        }
        """
    
    def _export_raw_data(self, df_metrics: pd.DataFrame, alerts_data: List, report_dir: Path):
        """Exporte les données brutes."""
        # CSV des métriques
        csv_path = report_dir / "metrics_data.csv"
        df_metrics.to_csv(csv_path, index=False, encoding='utf-8')
        
        # JSON des alertes
        alerts_json = []
        for alert in alerts_data:
            alerts_json.append({
                'alert_level': getattr(alert, 'alert_level', 'unknown'),
                'message': getattr(alert, 'message', ''),
                'metric_name': getattr(alert, 'metric_name', ''),
                'current_value': getattr(alert, 'current_value', 0),
                'threshold_value': getattr(alert, 'threshold_value', 0),
                'recommendations': getattr(alert, 'recommendations', [])
            })
        
        alerts_path = report_dir / "alerts_data.json"
        with open(alerts_path, 'w', encoding='utf-8') as f:
            json.dump(alerts_json, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📊 Données brutes exportées : {csv_path}, {alerts_path}")
    
    def _generate_empty_report(self, report_dir: Path, title: str) -> str:
        """Génère un rapport vide quand il n'y a pas de données."""
        html = f"""
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    padding: 50px; 
                    background-color: #f5f5f5; 
                }}
                .empty-report {{ 
                    background-color: white; 
                    padding: 50px; 
                    border-radius: 10px; 
                    box-shadow: 0 0 10px rgba(0,0,0,0.1); 
                }}
            </style>
        </head>
        <body>
            <div class="empty-report">
                <h1>{title}</h1>
                <h2>📊 Aucune donnée disponible</h2>
                <p>Aucune métrique d'extraction n'a été enregistrée.</p>
                <p>Effectuez quelques extractions de CV pour générer un rapport.</p>
            </div>
        </body>
        </html>
        """
        
        report_file = report_dir / "overfitting_report.html"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return str(report_file)


# Instance globale
overfitting_reporter = OverfittingReporter()
