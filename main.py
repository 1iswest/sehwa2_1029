import streamlit as st
st.title('은서')
st.subheader('집에 가고 싶다')
st.write('집에 가고 싶다ㅏㅏㅏㅏㅏㅏ')
st.write('https://naver.com')
st.link_button('네이버 바로가기', 'https://naver.com')

name=st.text_input('이름을 입력해주세요!:')
if st.button('환영인사'):
    st.write(name+'님 안녕')
    st.balloons()
st.success('에베벱')
st.warning('우엑')
st.error('오욍')
st.info('힣ㅎㅎㅎ')
