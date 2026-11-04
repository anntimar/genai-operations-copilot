# Arquitetura e decisões

1. A ingestão valida a extensão e o conteúdo, extrai texto, normaliza espaços, preserva a página do PDF e cria trechos sobrepostos. Trechos com padrões explícitos de injeção são descartados antes da indexação.
2. O PostgreSQL aplica filtros de documento, categoria e vigência antes de ranquear por distância vetorial e busca textual em português. A fusão por ranking recíproco evita comparar diretamente escalas distintas.
3. O fluxo LangGraph recebe pergunta, tarefa e candidatos. O mock seleciona evidência pelo vocabulário. O modelo configurável recebe os trechos como dados e propõe citações literais. O servidor verifica cada citação e devolve uma abstenção quando falta evidência.
4. A aplicação registra o histórico, as fontes utilizadas, o rastro, o custo estimado, a latência e o feedback. O histórico agrupa consultas por sessão e preserva o contexto para auditoria.
5. Solicitações críticas reconhecidas pelas regras geram uma revisão pendente. A transição de pendente para aprovada ou rejeitada é atômica. O projeto registra a decisão, sem integração com sistemas de pagamentos ou contas.

## Limitações e segurança

- O embedding padrão é hashing de termos, determinístico e sem downloads. Ele mede proximidade lexical e perde paráfrases com pouco vocabulário comum. Para similaridade semântica, configure um endpoint de embeddings com modelo multilíngue de 384 dimensões. Reingira o corpus ao mudar o modelo. A consulta usa apenas trechos do perfil de embeddings ativo.
- O backend SQLite serve para a demo local e usa pontuação diferente do PostgreSQL.
- A telemetria de tokens e custo cobre as chamadas de geração que retornam uso. A configuração opcional de embeddings externos tem cobrança separada.
- PDFs digitalizados exigem OCR externo. Uploads em produção também exigem limites no proxy e isolamento do parser.
- A detecção de prompt injection cobre padrões explícitos. A seleção extrativa, o teste de pertencimento e a ausência de ferramentas de execução reduzem o impacto. Citações literais podem conter regras incorretas se a fonte estiver incorreta.
- A autenticação de aprovação usa uma chave compartilhada. Sessões, uploads, exclusões e feedback pressupõem um ambiente local confiável. O histórico conserva trechos mesmo após a exclusão de documentos, para auditoria.
- Modelos externos recebem pergunta e trechos. Use documentos fictícios na demo. Logs da API excluem conteúdo dos documentos e perguntas.
- A classificação de ações críticas usa regras léxicas e a tarefa explícita. A escolha de tarefa é feita pelo usuário. Respostas seguem um formato extrativo e o histórico não é usado para resolver referências anafóricas.

## Roadmap

Calibração dos embeddings multilíngues e conjunto de avaliação com paráfrases e julgamentos humanos. Identidade de revisores, RBAC e isolamento por organização. Política de retenção e eliminação auditável. Monitoramento por operação e revisão das políticas com casos adversariais.
