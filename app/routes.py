from flask import render_template, request, jsonify
from . import db
from .models import Lead
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import os

def get_stage_label(stage_id):
    STAGE_LABELS = {
        "UC_A2DF81": "На согласовании",
        "IN_PROCESS": "Перезвонить",
        "CONVERTED": "Приглашен к рекрутеру"
    }
    return STAGE_LABELS.get(stage_id, stage_id)

def init_routes(app):
    @app.route('/')
    def dashboard():
        today = datetime.now().date()
        
        # Получаем данные за сегодня
        leads_today = Lead.query.filter(
            db.func.date(Lead.modified_date) == today
        ).all()
        
        # Статистика по стадиям
        stage_stats = {}
        for lead in leads_today:
            stage_label = get_stage_label(lead.stage_id)
            if stage_label not in stage_stats:
                stage_stats[stage_label] = 0
            stage_stats[stage_label] += 1
        
        # Статистика по операторам
        operator_stats = {}
        for lead in leads_today:
            if lead.operator_name not in operator_stats:
                operator_stats[lead.operator_name] = {}
            stage_label = get_stage_label(lead.stage_id)
            if stage_label not in operator_stats[lead.operator_name]:
                operator_stats[lead.operator_name][stage_label] = 0
            operator_stats[lead.operator_name][stage_label] += 1
        
        # График по часам
        time_ranges = [(i, i+1) for i in range(8, 20)]
        hourly_stats = {stage: [] for stage in stage_stats.keys()}
        
        for start_hour, end_hour in time_ranges:
            start_time = datetime.combine(today, datetime.min.time()).replace(hour=start_hour)
            end_time = datetime.combine(today, datetime.min.time()).replace(hour=end_hour)
            
            for stage in stage_stats.keys():
                count = Lead.query.filter(
                    db.func.lower(Lead.stage_label) == stage.lower(),
                    Lead.modified_date >= start_time,
                    Lead.modified_date < end_time
                ).count()
                hourly_stats[stage].append(count)
        
        plot_url = generate_plot(hourly_stats, time_ranges)
        
        return render_template('dashboard.html', 
                             stage_stats=stage_stats,
                             operator_stats=operator_stats,
                             plot_url=plot_url,
                             current_date=datetime.now().strftime('%d.%m.%Y'))

    def generate_plot(hourly_stats, time_ranges):
        plt.figure(figsize=(12, 6))
        
        for stage, counts in hourly_stats.items():
            x_labels = [f"{start}:00-{end}:00" for start, end in time_ranges]
            plt.plot(x_labels, counts, label=stage, marker='o')
        
        plt.title('Изменение количества лидов по стадиям по часам')
        plt.xlabel('Часы')
        plt.ylabel('Количество лидов')
        plt.legend()
        plt.grid()
        plt.xticks(rotation=45)
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight')
        buffer.seek(0)
        plot_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
        plt.close()
        
        return f"data:image/png;base64,{plot_data}"

    @app.route('/webhook', methods=['POST'])
    def webhook():
        data = request.json
        lead_data = data.get('data', {})
        
        lead = Lead.query.filter_by(lead_id=lead_data.get('ID')).first()
        if not lead:
            lead = Lead(
                lead_id=lead_data.get('ID'),
                stage_id=lead_data.get('STAGE_ID'),
                stage_label=get_stage_label(lead_data.get('STAGE_ID')),
                operator_id=lead_data.get('ASSIGNED_BY_ID'),
                operator_name=f"Оператор {lead_data.get('ASSIGNED_BY_ID')}",
                modified_date=datetime.strptime(lead_data.get('DATE_MODIFY'), '%Y-%m-%dT%H:%M:%S%z'),
                created_date=datetime.strptime(lead_data.get('DATE_CREATE'), '%Y-%m-%dT%H:%M:%S%z')
            )
        else:
            lead.stage_id = lead_data.get('STAGE_ID')
            lead.stage_label = get_stage_label(lead_data.get('STAGE_ID'))
            lead.modified_date = datetime.strptime(lead_data.get('DATE_MODIFY'), '%Y-%m-%dT%H:%M:%S%z')
        
        db.session.add(lead)
        db.session.commit()
        
        return jsonify({'status': 'success'})
