package com.yasusoft.abacml;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;

import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.wso2.balana.Balana;
import org.wso2.balana.PDP;
import org.wso2.balana.PDPConfig;
import org.wso2.balana.ParsingException;
import org.wso2.balana.ctx.AbstractResult;
import org.wso2.balana.ctx.ResponseCtx;
import org.wso2.balana.finder.impl.FileBasedPolicyFinderModule;
/**
 * XACML-based ABAC Middle Layer
 *
 */
public class ABACML
{
    private static Balana balana;
    public String name;
    public static void main(String[] args){
        initBalana();
	String request = createXACMLRequest("ubuntu", "GET", "/UOA_CANVAS_LMS/xamcl/STUDENTS/*");
	System.out.println("\n==================REQUEST===============\n");
	System.out.println(request);

	PDP pdp = getPDPNewInstance();
        String response = pdp.evaluate(request);
        System.out.println("\n==================RESPONCE===============\n");
        System.out.println(response);
    }

    public static String sayHello(String name){
        return "Hello, "+ name +"!";
    }

    public String sayHello(){
        return "Hello, "+ name +"!";
    }

    public static boolean Check_ABAC_Permission(String name, String action, String uri){
        initBalana();

        String request = createXACMLRequest(name, action, uri);
        //String request = createXACMLRequest("leomao", "GET", "/UOA_CANVAS_LMS/xamcl/STUDENTS/");
        PDP pdp = getPDPNewInstance();
        String response = pdp.evaluate(request);
        System.out.println(response);

        try {
            ResponseCtx responseCtx = ResponseCtx.getInstance(getXacmlResponse(response));
            AbstractResult result  = responseCtx.getResults().iterator().next();
            if(AbstractResult.DECISION_PERMIT == result.getDecision()){
                return true;
            } else {
                return false;
            }
        } catch (ParsingException e) {
            e.printStackTrace();
        }
        return false;
    }

    /**
     * Canonical-corpus entry point (benchmark harness only; not yet wired
     * into the Postgres/JNI path). Carries the full ABAC attribute set used
     * by the cross-engine benchmark corpus (see benchmark/docs/semantic-mapping.md
     * for the AttributeId convention) and returns the actual XACML decision
     * instead of collapsing Deny/NotApplicable/Indeterminate to false.
     *
     * Modeled on UOA Canvas LMS records, matching the existing
     * "/UOA_CANVAS_LMS/" convention already hardcoded in postgres.c: a
     * subject is a student/staff account with a role, home department, and
     * clearance level; a resource is a student-record table owned by a
     * department with a classification level; the action is the SQL verb
     * (SELECT/INSERT/UPDATE/DELETE) already extracted on the C side.
     *
     * @return one of "Permit", "Deny", "NotApplicable", "Indeterminate"
     */
    public static String Evaluate_ABAC_Decision(
            String subjectId, String subjectRole, String subjectDepartment, Integer subjectClearance,
            String resourceId, String resourceOwner, String resourceDepartment, Integer resourceClassification,
            String action,
            String envNetwork, Integer envHour) {

        initBalana();
        String request = createCanonicalXACMLRequest(
                subjectId, subjectRole, subjectDepartment, subjectClearance,
                resourceId, resourceOwner, resourceDepartment, resourceClassification,
                action, envNetwork, envHour);
        PDP pdp = getPDPNewInstance();
        String response = pdp.evaluate(request);
        return decisionToString(response);
    }

    private static String decisionToString(String response) {
        try {
            ResponseCtx responseCtx = ResponseCtx.getInstance(getXacmlResponse(response));
            AbstractResult result = responseCtx.getResults().iterator().next();
            int decision = result.getDecision();
            if (decision == AbstractResult.DECISION_PERMIT) {
                return "Permit";
            } else if (decision == AbstractResult.DECISION_DENY) {
                return "Deny";
            } else if (decision == AbstractResult.DECISION_NOT_APPLICABLE) {
                return "NotApplicable";
            } else {
                // DECISION_INDETERMINATE and its DENY/PERMIT/DENY_OR_PERMIT
                // variants all normalize to "Indeterminate" for the benchmark.
                return "Indeterminate";
            }
        } catch (ParsingException e) {
            e.printStackTrace();
            return "Indeterminate";
        }
    }

    public static Element getXacmlResponse(String response) {

        ByteArrayInputStream inputStream;
        DocumentBuilderFactory dbf;
        Document doc;

        inputStream = new ByteArrayInputStream(response.getBytes());
        dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);

        try {
            doc = dbf.newDocumentBuilder().parse(inputStream);
        } catch (Exception e) {
            System.err.println("DOM of request element can not be created from String");
            return null;
        } finally {
            try {
                inputStream.close();
            } catch (IOException e) {
               System.err.println("Error in closing input stream of XACML response");
            }
        }
        return doc.getDocumentElement();
    }


    private static void initBalana(){

        try{
            // using file based policy repository. so set the policy location as system property.
            // Only set the default if a caller (e.g. a test) hasn't already
            // pointed this at a different policy directory -- Balana caches
            // its configuration on first getInstance() call in this JVM, so
            // whichever directory is set first for a given process wins.
            if (System.getProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY) == null) {
                String policyLocation = (new File("/home/ubuntu/project/abacml")).getCanonicalPath() + File.separator + "resources";
                System.setProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY, policyLocation);
            }
        } catch (IOException e) {
            System.err.println("Can not locate policy repository");
        }
        // create default instance of Balana
        balana = Balana.getInstance();
    }

    private static PDP getPDPNewInstance(){

        PDPConfig pdpConfig = balana.getPdpConfig();

        return new PDP(pdpConfig);
    }

    public static String createXACMLRequest(String name, String action, String uri){

        return "<Request xmlns=\"urn:oasis:names:tc:xacml:3.0:core:schema:wd-17\" CombinedDecision=\"false\" ReturnPolicyIdList=\"false\">\n" +
                "<Attributes Category=\"urn:oasis:names:tc:xacml:1.0:subject-category:access-subject\">\n" +
                "<Attribute AttributeId=\"urn:oasis:names:tc:xacml:1.0:subject:subject-id\" IncludeInResult=\"false\">\n" +
                "<AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">" + name +"</AttributeValue>\n" +
                "</Attribute>\n" +
                "</Attributes>\n" +
                "<Attributes Category=\"urn:oasis:names:tc:xacml:3.0:attribute-category:action\">\n" +
                "<Attribute AttributeId=\"urn:oasis:names:tc:xacml:1.0:action:action-id\" IncludeInResult=\"false\">\n" +
                "<AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">" + action + "</AttributeValue>\n" +
                "</Attribute>\n" +
                "</Attributes>\n" +
                "<Attributes Category=\"urn:oasis:names:tc:xacml:3.0:attribute-category:resource\">\n" +
                "<Attribute AttributeId=\"urn:oasis:names:tc:xacml:1.0:resource:resource-id\" IncludeInResult=\"false\">\n" +
                "<AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">" + uri + "</AttributeValue>\n" +
                "</Attribute>\n" +
                "</Attributes>\n" +
                "</Request>";

    }

    /**
     * Builds a XACML 3.0 request carrying the full canonical UOA Canvas LMS
     * attribute set. AttributeIds for the fields not part of the base
     * XACML core schema (role, department, clearance, owner, classification,
     * network, hour) use the "urn:uoa:canvas:..." namespace documented in
     * benchmark/docs/semantic-mapping.md. Any null argument is simply
     * omitted from the request (MustBePresent="false" semantics achieved by
     * absence, matching how missing-attribute canonical scenarios are
     * represented).
     */
    public static String createCanonicalXACMLRequest(
            String subjectId, String subjectRole, String subjectDepartment, Integer subjectClearance,
            String resourceId, String resourceOwner, String resourceDepartment, Integer resourceClassification,
            String action,
            String envNetwork, Integer envHour) {

        StringBuilder sb = new StringBuilder();
        sb.append("<Request xmlns=\"urn:oasis:names:tc:xacml:3.0:core:schema:wd-17\" CombinedDecision=\"false\" ReturnPolicyIdList=\"false\">\n");

        sb.append("<Attributes Category=\"urn:oasis:names:tc:xacml:1.0:subject-category:access-subject\">\n");
        appendStringAttribute(sb, "urn:oasis:names:tc:xacml:1.0:subject:subject-id", subjectId);
        appendStringAttribute(sb, "urn:uoa:canvas:subject:role", subjectRole);
        appendStringAttribute(sb, "urn:uoa:canvas:subject:department", subjectDepartment);
        appendIntegerAttribute(sb, "urn:uoa:canvas:subject:clearance", subjectClearance);
        sb.append("</Attributes>\n");

        sb.append("<Attributes Category=\"urn:oasis:names:tc:xacml:3.0:attribute-category:action\">\n");
        appendStringAttribute(sb, "urn:oasis:names:tc:xacml:1.0:action:action-id", action);
        sb.append("</Attributes>\n");

        sb.append("<Attributes Category=\"urn:oasis:names:tc:xacml:3.0:attribute-category:resource\">\n");
        appendStringAttribute(sb, "urn:oasis:names:tc:xacml:1.0:resource:resource-id", resourceId);
        appendStringAttribute(sb, "urn:uoa:canvas:resource:owner", resourceOwner);
        appendStringAttribute(sb, "urn:uoa:canvas:resource:department", resourceDepartment);
        appendIntegerAttribute(sb, "urn:uoa:canvas:resource:classification", resourceClassification);
        sb.append("</Attributes>\n");

        sb.append("<Attributes Category=\"urn:oasis:names:tc:xacml:3.0:attribute-category:environment\">\n");
        appendStringAttribute(sb, "urn:uoa:canvas:environment:network", envNetwork);
        appendIntegerAttribute(sb, "urn:uoa:canvas:environment:hour", envHour);
        sb.append("</Attributes>\n");

        sb.append("</Request>");
        return sb.toString();
    }

    private static void appendStringAttribute(StringBuilder sb, String attributeId, String value) {
        if (value == null) {
            return;
        }
        sb.append("<Attribute AttributeId=\"").append(attributeId).append("\" IncludeInResult=\"false\">\n");
        sb.append("<AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#string\">")
          .append(escapeXml(value)).append("</AttributeValue>\n");
        sb.append("</Attribute>\n");
    }

    private static void appendIntegerAttribute(StringBuilder sb, String attributeId, Integer value) {
        if (value == null) {
            return;
        }
        sb.append("<Attribute AttributeId=\"").append(attributeId).append("\" IncludeInResult=\"false\">\n");
        sb.append("<AttributeValue DataType=\"http://www.w3.org/2001/XMLSchema#integer\">")
          .append(value).append("</AttributeValue>\n");
        sb.append("</Attribute>\n");
    }

    private static String escapeXml(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                     .replace("\"", "&quot;").replace("'", "&apos;");
    }
}
