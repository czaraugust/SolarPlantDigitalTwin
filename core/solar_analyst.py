import os
import threading
from google import genai
import statistics
from datetime import datetime

class SolarAnalyst:
    def __init__(self, api_key=None):
        """
        Inicializa o Analista Solar.
        :param api_key: Chave da API do Google Gemini. Se None, tenta ler de os.environ.
        """
        self.client = None
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") 
        if not self.api_key:
             # self.api_key = "..." # REMOVED FOR SECURITY
             pass

        self.buffer = []
        self.lock = threading.Lock()
        self.is_analyzing = False
        
        # --- MEMÓRIA DA IA ---
        self.conversation_history = []  # Contexto de Curto Prazo (últimas mensagens)
        self.daily_summaries = []       # Contexto de Longo Prazo (resumo dos dias)
        self.current_date = None        # Para detectar mudança de dia
        
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.model_name = 'gemini-2.5-pro' 
            except Exception as e:
                print(f"Erro ao configurar cliente Gemini: {e}")
                self.client = None
        else:
            print("AVISO: GEMINI_API_KEY não encontrada. O Analista Solar não funcionará.")
        
        self.on_analysis_callback = None # Callback para UI
        
        print(f"DEBUG: SolarAnalyst iniciado. API Key encontrada? {bool(self.api_key)}")

    def add_data_point(self, data_dict):
        """
        Adiciona um snapshot do sistema ao buffer.
        Thread-safe.
        """
        with self.lock:
            self.buffer.append(data_dict)
            if len(self.buffer) % 10 == 0:
                print(f"DEBUG: Buffer do Analista tem {len(self.buffer)} pontos.")
            
            # Dispara análise se tiver dados suficientes (ex: 60 segundos)
            if len(self.buffer) >= 60:
                if not self.client:
                    print("AVISO: Cliente Gemini não configurado. Limpando buffer...")
                    self.buffer = [] # Evita vazamento de memória
                    return

                if not self.is_analyzing:
                    print("DEBUG: Iniciando thread de análise...")
                    threading.Thread(target=self.analyze).start()
                else:
                    print("DEBUG: Análise já em andamento. Aguardando...")

    def process_buffer(self):
        """
        Calcula estatísticas agregadas do buffer.
        """
        if not self.buffer:
            return None

        # Estrutura para agregação
        aggregated = {}
        keys = self.buffer[0].keys()

        # Separar dados numéricos de strings
        numeric_data = {k: [] for k in keys if isinstance(self.buffer[0][k], (int, float))}
        string_data = {k: [] for k in keys if isinstance(self.buffer[0][k], str)}

        # Popula listas
        for point in self.buffer:
            for k in numeric_data:
                numeric_data[k].append(point.get(k, 0))
            for k in string_data:
                string_data[k].append(point.get(k, ""))

        # Calcula médias/min/max para numéricos
        for k, values in numeric_data.items():
            if values:
                aggregated[f"{k}_mean"] = statistics.mean(values)
                aggregated[f"{k}_min"] = min(values)
                aggregated[f"{k}_max"] = max(values)

        # Para strings (data/hora), pega o primeiro e o último
        if 'timestamp' in string_data:
            aggregated['start_time'] = string_data['timestamp'][0]
            aggregated['end_time'] = string_data['timestamp'][-1]
            
        return aggregated

    def analyze(self):
        """
        Dispara a análise para o agente de IA.
        Deve ser chamado em uma thread separada para não bloquear a UI.
        """
        if not self.client or self.is_analyzing:
            return

        with self.lock:
            if len(self.buffer) < 2: # Precisa de pelo menos alguns pontos
                return
            
            # Copia e limpa buffer
            data_snapshot = self.process_buffer()
            self.buffer = [] 
            self.is_analyzing = True

        try:
            # 1. Detectar Mudança de Dia
            sim_date = None
            try:
                # Tenta extrair a data do timestamp (formato YYYY-MM-DD HH:MM:SS)
                ts = data_snapshot.get('end_time', '')
                if ts:
                    sim_date = ts.split(' ')[0]
            except Exception:
                pass

            if sim_date and self.current_date and sim_date != self.current_date:
                # TROCA DE DIA DETECTADA
                self._handle_day_change(self.current_date)
            
            if sim_date:
                self.current_date = sim_date

            # 2. Construir Prompt com Memória
            prompt = self._construct_prompt(data_snapshot)
            
            # 3. Gerar Conteúdo
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            text_response = response.text
            
            # 4. Atualizar Memória de Curto Prazo
            self.conversation_history.append({"role": "user", "content": f"Dados: {str(data_snapshot)}"})
            self.conversation_history.append({"role": "model", "content": text_response})
            
            # Mantém apenas os últimos 3 turnos (6 mensagens) para economizar tokens
            if len(self.conversation_history) > 6:
                self.conversation_history = self.conversation_history[-6:]
            
            print("\n" + "="*50)
            print(f"ANÁLISE DO PERÍODO ENTRE {data_snapshot['start_time']} E {data_snapshot['end_time']}")
            print("="*50)
            print(text_response)
            print("="*50 + "\n")
            
            if self.on_analysis_callback:
                self.on_analysis_callback(data_snapshot['end_time'], text_response)

        except Exception as e:
            print(f"Erro na análise do Gemini: {e}")
        finally:
            self.is_analyzing = False

    def _handle_day_change(self, date_str):
        """
        Chamado quando o dia da simulação vira.
        Gera um resumo do dia que passou e guarda na memória de longo prazo.
        """
        print(f"DEBUG: Encerrando dia {date_str}. Gerando resumo...")
        
        # Se não há histórico, não há o que resumir
        if not self.conversation_history:
            return

        try:
            # Prompt de Resumão
            summary_prompt = f"""
            Analise o histórico de interações acima referente ao dia {date_str}.
            Gere um RESUMO EXECUTIVO (máximo 1 frase longa) sobre o desempenho geral do dia.
            Exemplo: "Dia 12/05: Geração solar estável com pico de 2000W, mas eficiência caiu à tarde devido a nuvens."
            """
            
            # Monta contexto temporário apenas para o resumo
            history_context = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in self.conversation_history])
            full_prompt = f"HISTÓRICO DO DIA {date_str}:\n{history_context}\n\n{summary_prompt}"
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt
            )
            
            summary = response.text.strip()
            self.daily_summaries.append(f"Dia {date_str}: {summary}")
            
            # Limpa memória de curto prazo para começar o novo dia limpo
            self.conversation_history = []
            
            print(f"RESUMO GERADO: {summary}")
            
        except Exception as e:
            print(f"Erro ao gerar resumo do dia: {e}")

    def _construct_prompt(self, data):
        """
        Cria o prompt para o especialista, injetando memórias.
        """
        # Monta o Contexto de Memória
        memory_section = ""
        
        # 1. Longo Prazo (Últimos 3 dias)
        if self.daily_summaries:
            last_days = self.daily_summaries[-3:]
            memory_section += "\nCONTEXTO DOS DIAS ANTERIORES:\n" + "\n".join(last_days) + "\n"
            
        # 2. Curto Prazo (Conversa recente)
        if self.conversation_history:
            memory_section += "\nÚLTIMAS ANÁLISES (Contexto Imediato):\n"
            # Mostra só as respostas do modelo para economizar espaço
            last_responses = [m['content'] for m in self.conversation_history if m['role'] == 'model']
            for i, resp in enumerate(last_responses[-2:], 1): # Pega as ultimas 2
                 memory_section += f"- Análise {i}: {resp[:200]}...\n" # Truncado
        
        return f"""
Atue como um Especialista Sênior em Geografia, Meteorologia e Energia Solar Fotovoltaica. 
Você é o cérebro que avalia um Gêmeo Digital de uma planta solar.

{memory_section}


DADOS ATUAIS ({data.get('start_time')} até {data.get('end_time')}):

0. LOCALIZAÇÃO & CONFIGURAÇÃO:
- Latitude: {data.get('latitude_mean'):.4f}
- Longitude: {data.get('longitude_mean'):.4f}
- Inclinação do Painel: {data.get('painel_tilt_mean'):.1f}°
- Azimute do Painel: {data.get('painel_azimute_config_mean'):.1f}°

1. CLIMA & AMBIENTE:
- Irradiância GHI (W/m²): Média {data.get('irradiancia_ghi_mean'):.1f} (Min {data.get('irradiancia_ghi_min'):.1f} / Max {data.get('irradiancia_ghi_max'):.1f})
- Temp. Ambiente (°C): Média {data.get('temp_amb_mean'):.1f}
- Temp. Painel (°C): Média {data.get('temp_painel_mean'):.1f}
- Vento: Velocidade {data.get('vento_vel_mean'):.1f} km/h
- Vento: Direção {data.get('vento_dir_mean'):.0f}°
- Chuva Acumulada (mm): {data.get('chuva_max'):.1f}
- Umidade (%): {data.get('umidade_mean'):.1f}
- Elevação do Sol: {data.get('elevacao_mean'):.1f}°
- Azimute do Sol: {data.get('azimute_mean'):.1f}°


2. PERFORMANCE ELÉTRICA (Painel Fixo):
- Potência REAL (W): Média {data.get('potencia_real_mean'):.1f}
- Potência PREVISTA (W): Média {data.get('potencia_meteo_mean'):.1f}
- Tensão (V): {data.get('tensao_real_mean'):.1f}
- Corrente (A): {data.get('corrente_real_mean'):.1f}

3. MÉTRICAS DE ERRO (Qualidade do Gêmeo Digital):
- MSE (W²): {data.get('mse_mean'):.2f}
- MAE (W): {data.get('mae_mean'):.2f}
- MAPE (%): {data.get('mape_mean'):.2f}%
- RMSE (W): {data.get('rmse_mean'):.2f}
- WAPE (%): {data.get('wape_mean'):.2f}%

TAREFA:
Faça uma análise crítica e concisa (máximo 3 parágrafos) cobrindo:
1. Comente a evolucao em relacao as analises anteriores (se houver no contexto).
2. Ambiente vs Geração: Correlacione a data do ano, hora do dia, elevação do sol, azimute do sol, localização da planta, inclinação do painel, azimute do painel, irradiância, temperatura ambiente e do painel, velocidade e direção do vento, chuva acumulada, umidade com a potência gerada.
3. Qualidade do Gêmeo: O modelo está aderente? Avalie as métricas de erro.

Se estiver de noite (Irradiância < 5 W/m²), informe apenas que o sistema está em repouso e ignore o resto.
"""
