from django.shortcuts import render
# from rest_framework.decorators import APIView
# from rest_framework.response import Response

def index(request):
    return render(request, 'index.html')


# from detection.kambyan_csv import*
# class ProcessVid(APIView):

#     def post(self, request):
#         #print(request.data['path'])
#         print(request.data['path'])
#         path_vid=request.data['path']
#         x = path_vid.split("/")
#         print(x[0])
     
#         object_list=main_process(x[0])

        
#         return Response({'message': object_list})